import pandas as pd
import numpy as np
import joblib
import uvicorn
import traceback
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from datetime import datetime
import requests
import os
import holidays
import calendar  # <--- IMPORTANTE: Para saber quantos dias tem no mês

# --- CONFIGURAÇÃO DA API ---
app = FastAPI(title="GridScope AI - Enterprise Core", version="4.0", port=8001)

# --- CARREGAMENTO DO MODELO ---
DIR_ATUAL = os.path.dirname(os.path.abspath(__file__))
MODEL_PATH = os.path.join(DIR_ATUAL, "modelo_consumo.pkl")

try:
    modelo_ia = joblib.load(MODEL_PATH)
    print(f"✅ Cérebro da IA carregado com sucesso: {MODEL_PATH}")
except:
    print("⚠️ Modelo ML não encontrado. O sistema usará fallback matemático.")
    modelo_ia = None

# --- MODELO DE DADOS (INPUT) ---
class DuckCurveRequest(BaseModel):
    data_alvo: str
    potencia_gd_kw: float
    consumo_mes_alvo_mwh: float  # <--- AGORA É MENSAL, NÃO ANUAL
    lat: float
    lon: float

# --- FUNÇÃO AUXILIAR DE CLIMA ---
def obter_clima(lat, lon, data_str):
    """ Busca irradiação e temperatura na Open-Meteo. """
    try:
        url = "https://api.open-meteo.com/v1/forecast"
        params = {
            "latitude": lat, "longitude": lon,
            "start_date": data_str, "end_date": data_str,
            "hourly": ["shortwave_radiation", "temperature_2m"],
            "timezone": "America/Sao_Paulo"
        }
        r = requests.get(url, params=params, timeout=3.0)
        
        if r.status_code == 200:
            data = r.json()
            if 'hourly' in data:
                rad = np.array(data['hourly']['shortwave_radiation'])
                temp = np.array(data['hourly']['temperature_2m'])
                if len(rad) == 24 and len(temp) == 24:
                    return rad, temp
    except Exception as e:
        print(f"   ⚠️ Clima API Error: {e}")
    
    # Fallback (Dia de sol padrão)
    rad = np.array([0,0,0,0,0,0, 50,200,450,700,850,950,900,800,600,350,150,20, 0,0,0,0,0,0])
    temp = np.array([25.0] * 24)
    return rad, temp

# --- ENDPOINT PRINCIPAL ---
@app.post("/predict/duck-curve")
def calcular_curva_inteligente(payload: DuckCurveRequest):
    print(f"\n🧠 IA Processando: Data={payload.data_alvo} | GD={payload.potencia_gd_kw}kW | Carga Mês={payload.consumo_mes_alvo_mwh:.2f}MWh")
    
    try:
        # --- 1. DATA PARSE E CALENDÁRIO ---
        try:
            dt = datetime.strptime(payload.data_alvo, "%Y-%m-%d")
        except:
            dt = datetime.now()
        
        br_holidays = holidays.Brazil()
        
        # Descobre quantos dias tem nesse mês específico (Ex: Fev 2024 = 29 dias)
        _, dias_no_mes = calendar.monthrange(dt.year, dt.month)
        
        # Calcula a média diária REAL baseada no dado do BDGD
        if payload.consumo_mes_alvo_mwh <= 0: payload.consumo_mes_alvo_mwh = 10.0 # Proteção
        media_diaria_mwh = payload.consumo_mes_alvo_mwh / dias_no_mes

        # --- 2. PREDIÇÃO DO PERFIL (FORMA DO BOLO) ---
        horas = np.arange(24)
        
        # Prepara o DataFrame exatamente como foi treinado (com a coluna ANO!)
        df_input = pd.DataFrame({
            "hora": horas,
            "mes": dt.month,
            "dia_semana": dt.weekday(),
            "eh_feriado": int(dt in br_holidays),
            "eh_fim_semana": int(dt.weekday() >= 5),
            "ano": dt.year, # <--- CRUCIAL: O novo modelo exige isso
            "dia_ano": dt.timetuple().tm_yday # Opcional, se usou no treino
        })

        # Garante que só mandamos as colunas que o modelo conhece
        if modelo_ia:
            try:
                colunas_modelo = modelo_ia.feature_names_in_
                df_filtrado = df_input[colunas_modelo]
                perfil_bruto = modelo_ia.predict(df_filtrado)
            except Exception as e:
                print(f"   ⚠️ Erro de Features na IA: {e}. Usando fallback.")
                perfil_bruto = 10 + 10 * np.exp(-(horas-19)**2/8) # Gaussiana
        else:
            perfil_bruto = 10 + 10 * np.exp(-(horas-19)**2/8)

        # --- 3. NORMALIZAÇÃO E ESCALONAMENTO ---
        # A IA previu um valor absoluto baseado no treino, mas precisamos ajustar
        # para a realidade exata da subestação vinda do BDGD.
        
        perfil_bruto = np.maximum(perfil_bruto, 0) # Remove negativos
        soma_perfil = perfil_bruto.sum()
        
        if soma_perfil == 0: soma_perfil = 1.0 # Evita div zero
        
        # Transforma a previsão em uma distribuição percentual (Forma)
        fator_forma = perfil_bruto / soma_perfil
        
        # Aplica essa forma ao volume diário real
        # AQUI É O PULO DO GATO: Se for feriado, a IA já "achatou" o perfil_bruto relativo a outros dias,
        # mas aqui forçamos o volume a bater com a média mensal.
        # Para ser PERFEITO, deveríamos ajustar a media_diaria baseado se hoje é feriado ou não
        # em relação à média do mês. Vamos fazer um ajuste fino:
        
        # Se a IA diz que hoje consome 20% menos que um dia normal, respeitamos isso.
        # Fator de ajuste do dia = (Soma Prevista Hoje) / (Média das Somas Previstas no Mês)
        # Simplificação robusta: Usamos a forma da IA aplicada à média.
        curve_consumo = fator_forma * media_diaria_mwh
        
        # Se for feriado, aplicamos um "redutor extra" se a média mensal for muito alta
        # (Opcional, mas ajuda a destacar a queda)
        if dt in br_holidays:
             # Se a média mensal vem cheia, mas hoje é feriado, reduzimos um pouco a média aplicada
             curve_consumo *= 0.85 

        # --- 4. GERAÇÃO SOLAR E CARGA LÍQUIDA ---
        rad, temp = obter_clima(payload.lat, payload.lon, payload.data_alvo)
        
        # Ajuste de tamanhos
        if len(rad) != 24: rad = np.resize(rad, 24)
        if len(temp) != 24: temp = np.resize(temp, 24)

        potencia_mw = payload.potencia_gd_kw / 1000.0
        
        # Modelo Físico PV
        perda_temp = (temp - 25).clip(min=0) * 0.004
        eficiencia_termica = 1 - perda_temp
        curve_geracao = potencia_mw * (rad / 1000.0) * 0.85 * eficiencia_termica

        curve_liquida = curve_consumo - curve_geracao

        # --- 5. ANÁLISE DE FLUXO ---
        min_net = np.min(curve_liquida)
        alerta = False
        analise = "✅ Operação Segura"
        
        if min_net < 0:
            analise = f"⚠️ ALERTA: Fluxo Reverso ({abs(min_net):.2f} MWh)"
            alerta = True
        elif np.min(curve_liquida) < (np.max(curve_consumo) * 0.2):
             analise = "⚠️ ATENÇÃO: Risco de Rampa (Duck Curve Profunda)"
             alerta = True

        return {
            "timeline": [f"{h:02d}:00" for h in range(24)],
            "consumo_mwh": np.round(curve_consumo, 3).tolist(),
            "geracao_mwh": np.round(curve_geracao, 3).tolist(),
            "carga_liquida_mwh": np.round(curve_liquida, 3).tolist(),
            "analise": analise,
            "alerta": alerta
        }

    except Exception as e:
        print("❌ ERRO CRÍTICO NA API:")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8001)