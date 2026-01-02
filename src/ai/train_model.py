import pandas as pd
import numpy as np
from sklearn.ensemble import RandomForestRegressor
import joblib
import os
import sys
import holidays

# Configura caminhos
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(os.path.dirname(current_dir))
MODELS_DIR = os.path.join(current_dir, "models")
os.makedirs(MODELS_DIR, exist_ok=True)

# Importa o ETL
sys.path.append(os.path.join(project_root, "src"))
from etl.etl_ai_consumo import buscar_dados_reais_para_ia

def treinar_modelo_subestacao(nome_sub, id_sub):
    print(f"\n🏗️ WORKER: Iniciando treino para {nome_sub} (ID: {id_sub})...")
    
    arquivo_modelo = os.path.join(MODELS_DIR, f"modelo_{id_sub}.pkl")
    
    # 1. Busca Dados (ETL Sherlock)
    dados_bdgd = buscar_dados_reais_para_ia(nome_sub)
    
    # Se falhar ou for fallback, ainda treinamos, mas avisamos
    if "erro" in dados_bdgd:
        print(f"⚠️ Aviso: Usando dados estimados para {nome_sub}")

    # 2. Gera Dataset
    df = gerar_dataset_interno(dados_bdgd)
    
    # 3. Treina
    features = ["hora", "mes", "dia_semana", "dia_ano", "ano", "eh_feriado", "eh_fim_semana"]
    modelo = RandomForestRegressor(n_estimators=100, n_jobs=-1, random_state=42)
    modelo.fit(df[features], df["consumo"])
    
    # 4. Salva com o ID no nome
    joblib.dump(modelo, arquivo_modelo)
    print(f"💾 Modelo salvo: {arquivo_modelo}")
    return True

def gerar_dataset_interno(dados_reais):
    # (Mesma lógica de antes, compactada para caber aqui)
    perfil_mensal = dados_reais['consumo_mensal']
    lista = []
    br_holidays = holidays.Brazil()
    anos = [2023, 2024]
    
    for ano in anos:
        datas = pd.date_range(f"{ano}-01-01", f"{ano}-12-31 23:00", freq="h")
        for data in datas:
            mes, hora = data.month, data.hour
            eh_fds = data.dayofweek >= 5
            eh_feriado = data.date() in br_holidays
            
            vol_mes = perfil_mensal.get(mes, 100)
            carga_media = (vol_mes * 1000) / 720
            
            fator = 1.0 + (0.4 * np.exp(-(hora - 11)**2 / 10)) + (0.7 * np.exp(-(hora - 19)**2 / 6))
            if hora < 6: fator *= 0.5
            if eh_fds or eh_feriado: fator *= 0.85
            
            lista.append({
                "consumo": carga_media * fator * np.random.normal(1, 0.05),
                "hora": hora, "mes": mes, "dia_semana": data.dayofweek,
                "dia_ano": data.dayofyear, "ano": ano,
                "eh_feriado": int(eh_feriado), "eh_fim_semana": int(eh_fds)
            })
    return pd.DataFrame(lista)