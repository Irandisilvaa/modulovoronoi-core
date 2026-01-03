import pandas as pd
import numpy as np
from sklearn.ensemble import RandomForestRegressor
from sklearn.model_selection import train_test_split
from sklearn.metrics import r2_score
import joblib
import os
import sys
import holidays
import warnings
from datetime import datetime

warnings.filterwarnings('ignore')

# --- CONFIGURAÇÃO DE CAMINHOS ROBUSTA ---
# Garante que o Python encontre a raiz do projeto e a pasta src
current_dir = os.path.dirname(os.path.abspath(__file__)) # src/ai
src_dir = os.path.dirname(current_dir)                   # src
project_root = os.path.dirname(src_dir)                  # raiz

sys.path.append(project_root)
sys.path.append(src_dir)

# Cria pasta de modelos se não existir
MODELS_DIR = os.path.join(current_dir, "models")
os.makedirs(MODELS_DIR, exist_ok=True)

try:
    from utils import carregar_dados_cache
    from etl.etl_ai_consumo import buscar_dados_reais_para_ia
except ImportError as e:
    print(f"⚠️ Aviso de Importação: {e}")
    # Fallback para execução isolada se necessário
    pass

# --- 1. DEFINIÇÃO DAS CURVAS DE COMPORTAMENTO ---
# (O DNA da Subestação usa isso para gerar o dataset de treino)
CURVAS_BASE = {
    "residencial": np.array([
        0.4, 0.35, 0.3, 0.3, 0.3, 0.35, # 00-05 (Madrugada baixa)
        0.5, 0.6, 0.6, 0.6, 0.6, 0.6,   # 06-11 (Manhã média)
        0.6, 0.6, 0.65, 0.7, 0.8, 0.9,  # 12-17 (Tarde subindo)
        1.0, 0.95, 0.9, 0.8, 0.6, 0.5   # 18-23 (Pico noturno)
    ]),
    "industrial": np.array([
        0.5, 0.5, 0.5, 0.5, 0.6, 0.8,   # Turnos noturnos constantes
        0.9, 1.0, 1.0, 1.0, 1.0, 0.9,   # Pico horário comercial
        0.8, 0.9, 1.0, 1.0, 1.0, 0.8,   # Tarde forte
        0.6, 0.5, 0.5, 0.5, 0.5, 0.5    # Queda pós-turno
    ]),
    "comercial": np.array([
        0.2, 0.2, 0.2, 0.2, 0.2, 0.3,   # Fechado
        0.5, 0.8, 0.9, 1.0, 1.0, 1.0,   # Abre lojas/escritórios
        1.0, 1.0, 1.0, 1.0, 0.9, 0.6,   # Tarde cheia
        0.4, 0.3, 0.2, 0.2, 0.2, 0.2    # Fecha tudo
    ]),
    "rural": np.array([
        0.4, 0.4, 0.4, 0.4, 0.6, 0.7,   # Acorda cedo
        0.8, 0.8, 0.8, 0.8, 0.8, 0.8,   # Irrigação/Maquinário dia
        0.8, 0.8, 0.8, 0.8, 0.7, 0.6,
        0.5, 0.5, 0.5, 0.4, 0.4, 0.4    # Dorme cedo
    ])
}

# --- 2. GERADOR DE DATASET (O "Cérebro" Lógico) ---
def gerar_dataset_inteligente(dados):
    """
    Cria dados sintéticos baseados no DNA da subestação (ex: 70% Residencial, 30% Ind).
    Isso ensina a IA como a subestação DEVE se comportar.
    """
    perfil_mensal = dados.get('consumo_mensal', {})
    if not perfil_mensal: 
        perfil_mensal = {m: 500 for m in range(1,13)}

    dna = dados.get('dna_perfil', {'residencial': 1.0})
    
    # Mistura as curvas base matematicamente
    curva_sintese = np.zeros(24)
    curva_sintese += CURVAS_BASE['residencial'] * dna.get('residencial', 0)
    curva_sintese += CURVAS_BASE['industrial'] * dna.get('industrial', 0)
    curva_sintese += CURVAS_BASE['comercial'] * dna.get('comercial', 0)
    curva_sintese += CURVAS_BASE['rural'] * dna.get('rural', 0)
    
    # Normalização segura
    soma_dna = sum([dna.get(k,0) for k in ['residencial','industrial','comercial','rural']])
    if soma_dna < 0.1: # Se DNA vier zerado, assume residencial
        curva_sintese = CURVAS_BASE['residencial']
    elif soma_dna < 1.0: # Completa com residencial se faltar %
        curva_sintese += CURVAS_BASE['residencial'] * (1.0 - soma_dna)

    # Evita divisão por zero
    media_curva = np.mean(curva_sintese)
    if media_curva > 0:
        curva_sintese = curva_sintese / media_curva

    lista = []
    br_holidays = holidays.Brazil()
    anos = [2023, 2024] # Treina com 2 anos de histórico simulado
    
    for ano in anos:
        try:
            datas = pd.date_range(f"{ano}-01-01", f"{ano}-12-31 23:00", freq="h")
        except:
            continue

        for data in datas:
            mes, hora = data.month, data.hour
            eh_fds = data.dayofweek >= 5
            eh_feriado = data.date() in br_holidays
            
            # Pega o volume total daquele mês (do ETL real)
            total_mes = perfil_mensal.get(mes, perfil_mensal.get(str(mes), 100))
            media_hora_base = (float(total_mes) / 30) / 24
            
            # Aplica a curva horária
            fator_hora = curva_sintese[hora]
            
            # Penalidade de Fim de Semana (Indústrias param, casas aumentam pouco)
            fator_fds = 1.0
            if eh_fds or eh_feriado:
                if dna.get('industrial', 0) > 0.5: 
                    fator_fds = 0.65 # Indústria cai muito
                elif dna.get('comercial', 0) > 0.5:
                    fator_fds = 0.50 # Comércio cai muito
                else:
                    fator_fds = 0.90 # Residencial cai pouco
            
            # Adiciona ruído aleatório para a IA não viciar (Overfitting)
            ruido = np.random.normal(1, 0.05) 
            
            consumo = media_hora_base * fator_hora * fator_fds * ruido
            
            lista.append({
                "consumo": abs(consumo),
                "hora": hora, 
                "mes": mes, 
                "dia_semana": data.dayofweek,
                "dia_ano": data.dayofyear, 
                "ano": ano,
                "eh_feriado": int(eh_feriado), 
                "eh_fim_semana": int(eh_fds)
            })
            
    return pd.DataFrame(lista)

# --- 3. FUNÇÃO DE TREINAMENTO (Chamada pelo Dashboard se o modelo não existir) ---
def treinar_modelo_subestacao(nome_sub_ou_id, dados_etl=None):
    """
    Treina um modelo Random Forest para a subestação específica.
    Pode receber dados_etl já buscados para economizar tempo.
    """
    print(f"\n🔄 [IA] Iniciando treinamento para: {nome_sub_ou_id}...")
    
    # Se não passou dados, busca agora
    if dados_etl is None:
        dados_etl = buscar_dados_reais_para_ia(nome_sub_ou_id)
    
    if "erro" in dados_etl and not dados_etl.get("alerta"):
        print(f"❌ Erro ETL: {dados_etl['erro']}")
        return None

    id_sub = str(dados_etl.get("id", "DEFAULT")).replace(" ", "_")
    
    # 1. Gera Dataset
    df = gerar_dataset_inteligente(dados_etl)
    if df.empty: return None

    # 2. Treina
    features = ["hora", "mes", "dia_semana", "dia_ano", "ano", "eh_feriado", "eh_fim_semana"]
    X = df[features]
    y = df["consumo"]
    
    # Random Forest rápido
    modelo = RandomForestRegressor(n_estimators=50, n_jobs=-1, random_state=42)
    modelo.fit(X, y)
    
    # 3. Salva
    caminho_modelo = os.path.join(MODELS_DIR, f"modelo_{id_sub}.pkl")
    joblib.dump(modelo, caminho_modelo)
    print(f"✅ Modelo treinado e salvo: {caminho_modelo}")
    
    return modelo, caminho_modelo

# --- 4. FUNÇÃO UNIFICADA DE PREVISÃO (Substitui o inference.py) ---
def prever_agora(id_sub, data_alvo, dados_etl, capacidade_gd_mw=0, fator_sol=1.0):
    """
    Função 'Tudo em Um':
    1. Verifica se tem modelo. Se não tiver, TREINA AGORA.
    2. Usa o modelo para prever as 24h.
    3. Calcula a Curva do Pato (Duck Curve).
    """
    id_limpo = str(id_sub).replace(" ", "_")
    path_modelo = os.path.join(MODELS_DIR, f"modelo_{id_limpo}.pkl")
    
    modelo = None
    
    # Tenta carregar
    if os.path.exists(path_modelo):
        modelo = joblib.load(path_modelo)
    else:
        # SE NÃO EXISTE, TREINA NA HORA (On-the-fly)
        print(f"⚠️ Modelo não encontrado para ID {id_sub}. Treinando agora...")
        modelo, _ = treinar_modelo_subestacao(dados_etl['subestacao'], dados_etl)
    
    if not modelo:
        # Se falhar tudo, retorna zero
        return pd.DataFrame({"hora": range(24), "consumo_mwh": [0]*24})

    # Prepara features para as 24h do dia escolhido
    if isinstance(data_alvo, str):
        data_alvo = pd.to_datetime(data_alvo)
        
    br_holidays = holidays.Brazil()
    eh_feriado = data_alvo.date() in br_holidays
    eh_fds = data_alvo.dayofweek >= 5
    
    features_dia = []
    for h in range(24):
        features_dia.append({
            "hora": h,
            "mes": data_alvo.month,
            "dia_semana": data_alvo.dayofweek,
            "dia_ano": data_alvo.dayofyear,
            "ano": data_alvo.year,
            "eh_feriado": int(eh_feriado),
            "eh_fim_semana": int(eh_fds)
        })
    
    # PREVISÃO DE CARGA (AI)
    consumo_horario = modelo.predict(pd.DataFrame(features_dia))
    
    # PREVISÃO SOLAR (Cálculo Físico Simples)
    horas = np.arange(24)
    curva_solar = np.exp(-((horas - 12)**2) / (2 * 2.5**2)) # Gaussiana meio-dia
    geracao_horaria = curva_solar * capacidade_gd_mw * fator_sol
    
    # CÁLCULO LÍQUIDO
    curva_liquida = consumo_horario - geracao_horaria

    return pd.DataFrame({
        "hora": horas,
        "consumo_mwh": np.maximum(consumo_horario, 0),
        "geracao_mwh": geracao_horaria,
        "carga_liquida_mwh": curva_liquida
    })

# --- BLOCO PRINCIPAL (Para teste via Terminal) ---
if __name__ == "__main__":
    if len(sys.argv) > 1:
        alvo = sys.argv[1]
        treinar_modelo_subestacao(alvo)
    else:
        # Tenta pegar um padrão do banco para testar
        try:
            from utils import carregar_dados_cache
            _, dados_lista = carregar_dados_cache()
            if dados_lista:
                nome = dados_lista[0]['subestacao']
                treinar_modelo_subestacao(nome)
            else:
                print("Nenhum dado no cache para teste.")
        except:
            print("Execute: python train_model.py 'NOME_DA_SUBESTACAO'")