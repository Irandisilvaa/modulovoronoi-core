import pandas as pd
import joblib
import uvicorn
import sys
import os
import holidays
import numpy as np  # Necessário para cálculos matemáticos da curva solar
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from datetime import datetime, timedelta

# --- 1. CONFIGURAÇÃO DE CAMINHOS ---
current_dir = os.path.dirname(os.path.abspath(__file__))
MODELS_DIR = os.path.join(current_dir, "models")

# Cache em memória para não ler do disco toda hora
CACHE_MODELOS = {}

app = FastAPI(
    title="GridScope AI - Inference Engine",
    version="6.1 (Voronoi + Duck Curve)",
    description="API híbrida: Inferência de Modelos ML + Simulação Matemática Energética."
)

# --- 2. MODELOS DE DADOS (Payloads) ---

# Modelo para previsão ML (Usa arquivos .pkl)
class PrevisaoRequest(BaseModel):
    subestacao_id: str  
    data_inicio: str    # YYYY-MM-DD
    horas_previsao: int = 24

# Modelo para a Duck Curve (Usa simulação matemática - O que o Dashboard pede)
class DuckCurveInput(BaseModel):
    data_alvo: str
    potencia_gd_kw: float
    consumo_mes_alvo_mwh: float
    lat: float
    lon: float

# --- 3. FUNÇÕES AUXILIARES ---

def carregar_modelo(sub_id: str):
    """Tenta carregar o modelo do cache ou do disco."""
    if sub_id in CACHE_MODELOS:
        return CACHE_MODELOS[sub_id]

    caminho_arquivo = os.path.join(MODELS_DIR, f"modelo_{sub_id}.pkl")
    
    if not os.path.exists(caminho_arquivo):
        return None

    try:
        print(f"📥 Carregando modelo do disco: {caminho_arquivo}")
        modelo = joblib.load(caminho_arquivo)
        CACHE_MODELOS[sub_id] = modelo
        return modelo
    except Exception as e:
        print(f"❌ Arquivo corrompido: {e}")
        return None

def gerar_features_futuras(data_inicio_str, horas=24):
    """Gera DataFrame de features temporais para o modelo ML."""
    try:
        data_start = datetime.strptime(data_inicio_str, "%Y-%m-%d")
    except ValueError:
        data_start = datetime.now()

    datas = [data_start + timedelta(hours=i) for i in range(horas)]
    br_holidays = holidays.Brazil()

    lista_dados = []
    for d in datas:
        lista_dados.append({
            "data_hora": d,
            "hora": d.hour,
            "mes": d.month,
            "dia_semana": d.weekday(),
            "dia_ano": d.timetuple().tm_yday,
            "ano": d.year,
            "eh_feriado": int(d.date() in br_holidays),
            "eh_fim_semana": int(d.weekday() >= 5)
        })
    
    return pd.DataFrame(lista_dados)

def simular_curva_solar(potencia_kw):
    """Simula uma curva de geração solar baseada em seno (06h as 18h)."""
    timeline = list(range(24))
    geracao = []
    # Fator de perda térmica estimado em 20% (0.8 eficiência)
    pico_mw = (potencia_kw * 0.8) / 1000 

    for h in timeline:
        if 6 <= h <= 18:
            # Curva senoidal simples
            fator = np.sin(((h - 6) * np.pi) / 12)
            valor = pico_mw * fator
            geracao.append(max(0, valor))
        else:
            geracao.append(0.0)
    return timeline, geracao

# --- 4. ENDPOINTS ---

@app.get("/")
def health_check():
    qtd_modelos = len([n for n in os.listdir(MODELS_DIR) if n.endswith('.pkl')]) if os.path.exists(MODELS_DIR) else 0
    return {
        "status": "online", 
        "arquitetura": "Hybrid (ML + Physics)",
        "endpoints": ["/predict (ML)", "/predict/duck-curve (Simulacao)"],
        "modelos_locais": qtd_modelos
    }

# ROTA 1: Machine Learning Puro (Requer modelo .pkl treinado)
@app.post("/predict")
def prever_consumo(dados: PrevisaoRequest):
    modelo = carregar_modelo(dados.subestacao_id)
    if modelo is None:
        raise HTTPException(status_code=404, detail=f"Modelo {dados.subestacao_id} não encontrado.")

    try:
        df_futuro = gerar_features_futuras(dados.data_inicio, dados.horas_previsao)
        features = ["hora", "mes", "dia_semana", "dia_ano", "ano", "eh_feriado", "eh_fim_semana"]
        previsao_valores = modelo.predict(df_futuro[features])
        
        resposta = []
        for i, valor in enumerate(previsao_valores):
            resposta.append({
                "data": df_futuro.iloc[i]["data_hora"].strftime("%Y-%m-%d %H:%M:%S"),
                "consumo_kwh": float(valor) if valor > 0 else 0.0
            })

        return {"sub_id": dados.subestacao_id, "previsoes": resposta}

    except Exception as e:
        print(f"Erro interno ML: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# ROTA 2: Duck Curve / Simulação (ESSA É A QUE O DASHBOARD ESTÁ PEDINDO)
@app.post("/predict/duck-curve")
def predict_duck_curve(entrada: DuckCurveInput):
    """
    Calcula a 'Curva de Pato': Consumo Típico vs Geração Solar Estimada.
    Não precisa de modelo .pkl, usa matemática direta.
    """
    try:
        # 1. Estimar Consumo Diário (Média simples do mensal)
        consumo_diario_mwh = entrada.consumo_mes_alvo_mwh / 30
        
        # 2. Criar Perfil de Carga Horária Típico (Residencial/Misto)
        timeline = list(range(24))
        # Percentual de consumo por hora (pico à noite)
        perfil_horario = [
            0.03, 0.02, 0.02, 0.02, 0.03, 0.04, # Madrugada
            0.05, 0.06, 0.05, 0.04, 0.04, 0.04, # Manhã
            0.04, 0.04, 0.05, 0.06, 0.07, 0.09, # Tarde
            0.12, 0.10, 0.09, 0.08, 0.06, 0.04  # Noite (Pico)
        ]
        carga_horaria = [p * consumo_diario_mwh for p in perfil_horario]
        
        # 3. Simular Geração Solar
        _, geracao_solar = simular_curva_solar(entrada.potencia_gd_kw)
        
        # 4. Calcular Carga Líquida (Duck Curve)
        carga_liquida = []
        alerta_inversao = False
        
        for c, g in zip(carga_horaria, geracao_solar):
            saldo = c - g
            carga_liquida.append(saldo)
            if saldo < 0:
                alerta_inversao = True

        return {
            "status": "success",
            "analise": "Risco de Inversão de Fluxo" if alerta_inversao else "Operação Segura",
            "alerta": alerta_inversao,
            "timeline": timeline,
            "consumo_mwh": carga_horaria,
            "geracao_mwh": geracao_solar,
            "carga_liquida_mwh": carga_liquida
        }

    except Exception as e:
        print(f"Erro na Duck Curve: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# --- 5. EXECUÇÃO ---
if __name__ == "__main__":
    if not os.path.exists(MODELS_DIR):
        os.makedirs(MODELS_DIR)
        print(f"📁 Pasta criada: {MODELS_DIR}")
    
    print(f"🚀 API GridScope AI rodando na porta 8001...")
    # Roda ouvindo em todas as interfaces
    uvicorn.run(app, host="0.0.0.0", port=8001)