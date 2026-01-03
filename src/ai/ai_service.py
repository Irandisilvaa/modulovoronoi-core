import pandas as pd
import joblib
import uvicorn
import sys
import os
import holidays
import numpy as np
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime, timedelta

# --- 1. CONFIGURAÇÃO DE CAMINHOS ---
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(os.path.dirname(current_dir))
MODELS_DIR = os.path.join(current_dir, "models")

# Importa utilitários de clima (se existir)
sys.path.append(os.path.join(project_root, "src"))
try:
    from etl.etl_ai_consumo import obter_irradiacao_solar_real
except ImportError:
    obter_irradiacao_solar_real = None

CACHE_MODELOS = {}

app = FastAPI(
    title="GridScope AI - Inference Engine",
    version="8.0 (Dashboard Compatible)",
    description="API Híbrida otimizada para integração com Streamlit."
)

# --- 2. MODELOS DE DADOS (Payload Compatível com o Dashboard) ---

class DuckCurveInput(BaseModel):
    # Campos que o Dashboard envia:
    data_alvo: str          
    potencia_gd_kw: float   
    consumo_mes_alvo_mwh: float 
    lat: float
    lon: float
    
    # Campo opcional (O Dashboard não está enviando, mas a IA pode usar se receber)
    subestacao_id: Optional[str] = None 

# --- 3. FUNÇÕES AUXILIARES ---

def carregar_modelo(sub_id: str):
    """Tenta carregar o modelo treinado específico da subestação."""
    if not sub_id: return None
    
    if sub_id in CACHE_MODELOS:
        return CACHE_MODELOS[sub_id]

    nomes_possiveis = [
        f"modelo_{sub_id}.pkl",
        f"modelo_{sub_id.replace(' ', '_')}.pkl",
        f"modelo_{sub_id.upper()}.pkl"
    ]
    
    caminho_final = None
    for nome in nomes_possiveis:
        p = os.path.join(MODELS_DIR, nome)
        if os.path.exists(p):
            caminho_final = p
            break
            
    if not caminho_final:
        return None

    try:
        modelo = joblib.load(caminho_final)
        CACHE_MODELOS[sub_id] = modelo
        return modelo
    except Exception as e:
        print(f"❌ Erro ao ler pickle: {e}")
        return None

def gerar_features_para_predicao(data_str):
    """Gera timeline de 0 a 23h com features temporais."""
    try:
        data_base = datetime.strptime(data_str, "%Y-%m-%d")
    except ValueError:
        data_base = datetime.now()

    br_holidays = holidays.Brazil()
    lista = []
    
    for h in range(24):
        d = data_base + timedelta(hours=h)
        lista.append({
            "hora": d.hour,
            "mes": d.month,
            "dia_semana": d.weekday(),
            "dia_ano": d.timetuple().tm_yday,
            "ano": d.year,
            "eh_feriado": int(d.date() in br_holidays),
            "eh_fim_semana": int(d.weekday() >= 5)
        })
    return pd.DataFrame(lista)

def simular_solar_fallback(potencia_kw):
    """Gera curva solar matemática se a API de clima falhar."""
    geracao = []
    # Converte kW para MW e aplica eficiência
    pico_mw = (potencia_kw * 0.85) / 1000 
    for h in range(24):
        if 6 <= h <= 18:
            val = np.sin(((h - 6) * np.pi) / 12) * pico_mw
            geracao.append(max(0, val))
        else:
            geracao.append(0.0)
    return geracao

# --- 4. ENDPOINTS ---

@app.post("/predict/duck-curve")
def predict_duck_curve(entrada: DuckCurveInput):
    """
    Endpoint ajustado para garantir resposta válida mesmo sem ID da subestação.
    Retorna exatamente os campos que o Dashboard espera:
    ['timeline', 'consumo_mwh', 'geracao_mwh', 'carga_liquida_mwh', 'analise', 'alerta']
    """
    try:
        timeline = list(range(24))
        
        # 1. Tenta carregar IA (Se ID vier nulo, usa genérico)
        modelo = carregar_modelo(entrada.subestacao_id)
        
        # Gera features
        df_input = gerar_features_para_predicao(entrada.data_alvo)
        cols_treino = ["hora", "mes", "dia_semana", "dia_ano", "ano", "eh_feriado", "eh_fim_semana"]
        
        perfil_percentual = []
        
        if modelo:
            # IA Específica
            predicao_bruta = modelo.predict(df_input[cols_treino])
            total_predito = np.sum(predicao_bruta)
            if total_predito > 0:
                perfil_percentual = predicao_bruta / total_predito
            else:
                perfil_percentual = [1/24] * 24
        else:
            # Perfil Genérico (Residencial "Padrão" Brasileiro)
            # Usado quando o dashboard não manda o ID ou o modelo não existe
            lista_fixa = [
                0.03, 0.02, 0.02, 0.02, 0.03, 0.04, # Madrugada
                0.05, 0.06, 0.05, 0.04, 0.04, 0.04, # Manhã
                0.04, 0.04, 0.05, 0.06, 0.07, 0.09, # Tarde
                0.12, 0.10, 0.09, 0.08, 0.06, 0.04  # Noite (Pico)
            ]
            total_f = sum(lista_fixa)
            perfil_percentual = [x/total_f for x in lista_fixa]

        # 2. Define Volume (Consumo Mensal / 30)
        volume_diario_mwh = entrada.consumo_mes_alvo_mwh / 30
        
        # Aplica Volume no Perfil
        curva_consumo = [float(p * volume_diario_mwh) for p in perfil_percentual]

        # 3. Geração Solar
        curva_solar = []
        usou_clima_real = False
        if obter_irradiacao_solar_real:
            try:
                rads = obter_irradiacao_solar_real(entrada.lat, entrada.lon, entrada.data_alvo)
                if rads:
                    # kW * Radiação normalizada * Eficiência -> MW
                    curva_solar = [float((entrada.potencia_gd_kw * (r/1000.0) * 0.85) / 1000.0) for r in rads]
                    usou_clima_real = True
            except:
                pass
        
        if not curva_solar or sum(curva_solar) == 0:
            curva_solar = simular_solar_fallback(entrada.potencia_gd_kw)

        # 4. Carga Líquida e Análise
        carga_liquida = []
        minima_liquida = 999999
        alerta = False
        
        for c, g in zip(curva_consumo, curva_solar):
            saldo = c - g
            carga_liquida.append(saldo)
            if saldo < minima_liquida: minima_liquida = saldo

        # Lógica de Diagnóstico para o Dashboard
        status_msg = "Operação Normal"
        if minima_liquida < 0:
            status_msg = "Inversão de Fluxo (Risco Crítico)"
            alerta = True
        elif minima_liquida < (max(curva_consumo) * 0.3):
            status_msg = "Duck Curve Acentuada (Atenção)"
            # Não necessariamente um alerta vermelho, mas um aviso
        
        # Retorno no formato exato que o Dashboard espera
        return {
            "status": "success",
            "analise": status_msg,
            "alerta": alerta,
            "timeline": timeline,
            "consumo_mwh": curva_consumo,
            "geracao_mwh": curva_solar,
            "carga_liquida_mwh": carga_liquida,
            "metadados": {
                "origem_perfil": "IA Treinada" if modelo else "Genérico (Fallback)",
                "origem_solar": "Clima Real (Open-Meteo)" if usou_clima_real else "Estimativa Teórica"
            }
        }

    except Exception as e:
        print(f"Erro Interno API: {e}")
        # Retorna 500 para o dashboard tratar
        raise HTTPException(status_code=500, detail=str(e))
