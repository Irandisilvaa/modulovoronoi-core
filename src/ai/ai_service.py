import pandas as pd
import numpy as np
import joblib
import uvicorn
import traceback
import sys
import os
import requests
import holidays
import calendar   
import geopandas as gpd
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from datetime import datetime
from shapely.geometry import Point
from scipy.ndimage import gaussian_filter1d

# --- TENTATIVA DE IMPORTAR CONFIGURAÇÃO ---
try:
    sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))
    from config import PATH_GDB
except ImportError:
    PATH_GDB = "C:/BDGD/BDGD.gdb" # Caminho Fallback

# --- CONFIGURAÇÃO DA APP ---
app = FastAPI(title="GridScope AI - Enterprise Full", version="7.0 Final-Fix")

DIR_ATUAL = os.path.dirname(os.path.abspath(__file__))
SUBESTACOES_GEOJSON = os.path.join(DIR_ATUAL, "subestacoes_logicas.geojson")
MODEL_PATH = os.path.join(DIR_ATUAL, "modelo_consumo.pkl")

# ==============================================================================
# 1. MÓDULO ETL (EXTRAÇÃO DE DADOS REAIS - CONFIRMADO KWH)
# ==============================================================================
def normalizar_id(valor):
    if pd.isna(valor): return ""
    s = str(valor).strip().replace('.0', '')
    return s

def buscar_dados_reais_interno(nome_subestacao, mes_alvo):
    """
    Busca no GDB a soma de energia para o mês alvo.
    Retorna float (kWh).
    """
    if not os.path.exists(PATH_GDB):
        print(f"⚠️ GDB não encontrado.")
        return None

    try:
        print(f"🔎 Buscando: {nome_subestacao} (Mês: {mes_alvo})")
        
        # 1. Identificar ID da Subestação
        try:
            sample = gpd.read_file(PATH_GDB, layer='SUB', engine='pyogrio', rows=1)
            cols = sample.columns.tolist()
            col_nome = next((c for c in cols if c.upper() in ['NOM', 'NOME', 'NAME', 'PAC_1']), None)
            col_id = next((c for c in cols if c.upper() in ['COD_ID', 'ID', 'CODIGO', 'SUB']), None)

            if not col_nome or not col_id: return None

            gdf_sub = gpd.read_file(PATH_GDB, layer='SUB', engine='pyogrio', columns=[col_nome, col_id])
            filtro = gdf_sub[col_nome].astype(str).str.upper().str.contains(str(nome_subestacao).strip().upper(), na=False)
            
            if filtro.sum() == 0: return None

            id_alvo = normalizar_id(gdf_sub[filtro].iloc[0][col_id])
            print(f"   -> ID Localizado: {id_alvo}")
            
        except Exception as e:
            print(f"❌ Erro SUB: {e}")
            return None

        # 2. Ler Consumo na layer UCBT
        try:
            layers = gpd.list_layers(PATH_GDB)['name'].tolist()
            layer_uc = 'UCBT' if 'UCBT' in layers else 'UCBT_tab'
            
            # Pega amostra para achar a coluna do mês
            sample_uc = gpd.read_file(PATH_GDB, layer=layer_uc, engine='pyogrio', rows=1)
            cols_uc = sample_uc.columns.tolist()
            
            # Busca coluna ENE_01, ENE_02, etc. baseada no mês numérico
            col_mes = None
            for c in cols_uc:
                if c.upper().startswith('ENE'):
                    parts = c.split('_')
                    if len(parts) > 1 and parts[1].isdigit():
                        if int(parts[1]) == int(mes_alvo):
                            col_mes = c
                            break
            
            if not col_mes:
                print(f"❌ Coluna do mês {mes_alvo} não achada.")
                return None

            # Lê dados
            df_uc = gpd.read_file(PATH_GDB, layer=layer_uc, engine='pyogrio', columns=['SUB', col_mes], ignore_geometry=True)
            df_uc['SUB_STR'] = df_uc['SUB'].apply(normalizar_id)
            
            # SOMA DIRETA (CONFIRMADO QUE ESTÁ EM KWH)
            total_kwh = df_uc[df_uc['SUB_STR'] == id_alvo][col_mes].sum()
            total_kwh = float(total_kwh)
            
            print(f"   -> Soma kWh encontrada: {total_kwh:,.0f}")
            return total_kwh

        except Exception as e:
            print(f"❌ Erro UCBT: {e}")
            return None

    except Exception as e:
        print(f"❌ Erro Geral: {e}")
        return None

# ==============================================================================
# 2. CARREGAMENTO MODELOS
# ==============================================================================
model_rf = None
if os.path.exists(MODEL_PATH):
    try: model_rf = joblib.load(MODEL_PATH)
    except: pass
gdf_subs = None
if os.path.exists(SUBESTACOES_GEOJSON):
    try: gdf_subs = gpd.read_file(SUBESTACOES_GEOJSON).to_crs(epsg=4326)
    except: pass

# ==============================================================================
# 3. LÓGICA DA API
# ==============================================================================
class DuckCurveRequest(BaseModel):
    data_alvo: str
    potencia_gd_kw: float
    consumo_mes_alvo_mwh: float 
    lat: float
    lon: float
    dna_perfil: dict | None = None 

def resolver_subestacao(lat, lon):
    if gdf_subs is None or gdf_subs.empty: return "Desconhecida"
    try:
        ponto = gpd.GeoDataFrame(geometry=[Point(lon, lat)], crs="EPSG:4326")
        join = gpd.sjoin(ponto, gdf_subs, how="left", predicate="within")
        if not join.empty:
            return str(join.iloc[0].get('NOM', join.iloc[0].get('nome', 'Subestação')))
    except: pass
    return "Não Mapeada"

def obter_clima(lat, lon, data_str):
    """
    Retorna irradiação solar com formato de sino garantido.
    """
    try:
        url = "https://api.open-meteo.com/v1/forecast"
        params = {
            "latitude": lat, "longitude": lon, 
            "start_date": data_str, "end_date": data_str, 
            "hourly": ["shortwave_radiation", "temperature_2m"], 
            "timezone": "America/Sao_Paulo"
        }
        r = requests.get(url, params=params, timeout=3)
        if r.status_code == 200:
            d = r.json()
            r_api = np.array(d["hourly"]["shortwave_radiation"])
            t_api = np.array(d["hourly"]["temperature_2m"])
            
            # Verifica se temos dados válidos
            if len(r_api) == 24 and np.max(r_api) > 0:
                return r_api, t_api
    except:
        pass
    
    # Fallback: Curva de sino padrão (aproximação de dia ensolarado)
    # Formato: baixo à noite, crescente pela manhã, pico ao meio-dia, decrescente à tarde
    horas = np.arange(24)
    # Curva gaussiana centrada nas 12h
    rad = 1000 * np.exp(-((horas - 12) ** 2) / (2 * 3.5 ** 2))
    # Garante que durante a noite seja zero
    rad[(horas < 6) | (horas > 18)] = 0
    temp = 25 + 5 * np.sin((horas - 14) * np.pi / 12)
    
    return rad, temp

def prever_curva_ml(data_alvo, dna):
    if not dna: dna = {"residencial": 0.4, "comercial": 0.3, "industrial": 0.3, "rural": 0.0}
    br_holidays = holidays.Brazil()
    eh_feriado = int(data_alvo.date() in br_holidays)
    eh_fds = int(data_alvo.weekday() >= 5)
    
    features = []
    for h in range(24):
        features.append({
            "hora": h, "mes": data_alvo.month, "dia_semana": data_alvo.weekday(),
            "eh_feriado": eh_feriado, "eh_fim_semana": eh_fds,
            "pct_residencial": float(dna.get('residencial',0)),
            "pct_comercial": float(dna.get('comercial',0)),
            "pct_industrial": float(dna.get('industrial',0)),
            "pct_rural": float(dna.get('rural',0))
        })
    
    if model_rf:
        try: return model_rf.predict(pd.DataFrame(features))
        except: pass
    
    t = np.linspace(0, 24, 24)
    return np.maximum(10 + 5 * np.sin((t - 10) * np.pi / 12), 0.1)

@app.post("/predict/duck-curve")
def calcular_curva_inteligente(payload: DuckCurveRequest):
    try:
        sub_nome = resolver_subestacao(payload.lat, payload.lon)
        try:
            dt = datetime.strptime(payload.data_alvo, "%Y-%m-%d")
        except:
            dt = datetime.now()

        # --- 1. CONSUMO (Confiança no GDB) ---
        consumo_real = buscar_dados_reais_interno(sub_nome, dt.month)
        
        if consumo_real and consumo_real > 0:
            consumo_mes_final_kwh = consumo_real
            origem = "GDB (Real)"
        else:
            # Se falhar o GDB, usa o input e garante escala kWh
            val = float(payload.consumo_mes_alvo_mwh)
            consumo_mes_final_kwh = val * 1000.0 if val < 50000 else val
            origem = "Estimado"

        # --- 2. POTÊNCIA GD (W vs kW) ---
        pot_gd_input = float(payload.potencia_gd_kw)
        
        # Lógica inteligente: Se a GD for maior que 50% do consumo MENSAL, 
        # provavelmente o usuário digitou Watts em vez de kW.
        razao = pot_gd_input / consumo_mes_final_kwh if consumo_mes_final_kwh != 0 else 0
        if razao > 0.5: 
            print(f"⚠️ Potência GD suspeita ({pot_gd_input}). Convertendo W -> kW.")
            pot_gd_final_kw = pot_gd_input / 1000.0
        else:
            pot_gd_final_kw = pot_gd_input

        print(f"📊 CÁLCULO: Consumo={consumo_mes_final_kwh:,.0f} kWh ({origem}) | GD={pot_gd_final_kw:.2f} kW")

        # --- 3. Distribuição Horária com normalização ---
        _, dias_no_mes = calendar.monthrange(dt.year, dt.month)
        media_diaria_kwh = consumo_mes_final_kwh / dias_no_mes if dias_no_mes > 0 else consumo_mes_final_kwh

        curva_shape = prever_curva_ml(dt, payload.dna_perfil)

        # NORMALIZAÇÃO: Garante que a curva tenha amplitude consistente
        if curva_shape.max() > 0:
            curva_shape = curva_shape / curva_shape.max()  # Normaliza para 0-1
        else:
            curva_shape = np.ones(24) * 0.5  # Fallback
            
        # Perfil típico de consumo diário
        perfil_tipico = np.array([
            0.3, 0.25, 0.2, 0.18, 0.2, 0.3, 0.5,  # 0-6h
            0.8, 0.9, 0.85, 0.8, 0.75, 0.7,       # 7-12h  
            0.8, 0.9, 1.0, 0.95, 0.9, 0.85,       # 13-18h
            0.7, 0.6, 0.5, 0.4, 0.35              # 19-23h
        ])
        
        # Combina a previsão ML com o perfil típico
        curva_combinada = 0.7 * curva_shape + 0.3 * perfil_tipico
        
        # Normaliza para bater com a média diária
        soma_shape = curva_combinada.sum()
        if soma_shape == 0: 
            soma_shape = 1
            
        # Fator de escala baseado no tipo de consumo (mantive sua lógica)
        dna = payload.dna_perfil or {}
        try:
            dna_res = float(dna.get('residencial', 0))
            dna_com = float(dna.get('comercial', 0))
            dna_ind = float(dna.get('industrial', 0))
            dna_rur = float(dna.get('rural', 0))
        except Exception:
            dna_res, dna_com, dna_ind, dna_rur = 0.4, 0.3, 0.3, 0.0

        soma_dna = dna_res + dna_com + dna_ind + dna_rur
        if soma_dna <= 0:
            # fallback seguro
            dna_res, dna_com, dna_ind, dna_rur = 0.4, 0.3, 0.3, 0.0
            soma_dna = 1.0

        # normaliza para garantir soma = 1.0
        dna_res /= soma_dna; dna_com /= soma_dna; dna_ind /= soma_dna; dna_rur /= soma_dna
        dna_usado = {"residencial": dna_res, "comercial": dna_com, "industrial": dna_ind, "rural": dna_rur}

        fator_escala = 1.0
        if dna_ind > 0.5:
            fator_escala = 1.2
        elif dna_res > 0.7:
            fator_escala = 0.8
            
        curve_consumo = curva_combinada * (media_diaria_kwh / soma_shape) * fator_escala
        
        # --- 4. Geração Solar com formato de sino garantido ---
        rad, temp = obter_clima(payload.lat, payload.lon, payload.data_alvo)
        eficiencia_temp = 1.0 - np.clip((temp - 25.0) * 0.004, 0.0, 0.2)
        
        # FÓRMULA AJUSTADA: P(kW) * Irrad(kW/m2) * PR * fator_diurno
        horas = np.arange(24)
        fator_diurno = np.exp(-((horas - 12) ** 2) / (2 * 4 ** 2))
        fator_diurno[(horas < 6) | (horas > 19)] = 0
        
        curve_geracao = pot_gd_final_kw * (rad / 1000.0) * 0.85 * eficiencia_temp * fator_diurno
        
        # Suaviza a curva de geração
        if len(curve_geracao) > 0:
            curve_geracao = gaussian_filter1d(curve_geracao, sigma=1.0)
        
        curve_liquida = curve_consumo - curve_geracao
        
        # Garante valores mínimos para visualização (mantive sua proteção)
        min_visivel = max(curve_consumo.min() * 0.1, 1.0)
        curve_consumo = np.maximum(curve_consumo, min_visivel)

        # consumo por classe horário (kW/h) — já existia, mas aqui garantimos com dna_usado
        consumo_res_kwh = np.round(curve_consumo * dna_res, 3).tolist()
        consumo_com_kwh = np.round(curve_consumo * dna_com, 3).tolist()
        consumo_ind_kwh = np.round(curve_consumo * dna_ind, 3).tolist()

        # consumo mensal por classe — distribuído para o mês alvo (kWh)
        consumo_mensal_por_classe = {
            int(dt.month): {
                "residencial": float(consumo_mes_final_kwh * dna_res),
                "comercial": float(consumo_mes_final_kwh * dna_com),
                "industrial": float(consumo_mes_final_kwh * dna_ind),
                "rural": float(consumo_mes_final_kwh * dna_rur)
            }
        }

        return {
            "subestacao": sub_nome,
            "timeline": [f"{h:02d}:00" for h in range(24)],
            "consumo_kwh": np.round(curve_consumo, 3).tolist(),
            "geracao_kwh": np.round(curve_geracao, 3).tolist(),
            "carga_liquida_kwh": np.round(curve_liquida, 3).tolist(),
            "consumo_res_kwh": consumo_res_kwh,
            "consumo_com_kwh": consumo_com_kwh,
            "consumo_ind_kwh": consumo_ind_kwh,
            "consumo_mes_alvo_kwh": float(consumo_mes_final_kwh),
            "origem_consumo": origem,
            "pot_gd_final_kw": float(pot_gd_final_kw),
            "dna_perfil_usado": dna_usado,
            "consumo_mensal_por_classe": consumo_mensal_por_classe,  # mês alvo apenas
            "alerta": bool(np.min(curve_liquida) < 0),
            "analise": f"Carga Média: {media_diaria_kwh/24:.0f} kW | GD: {pot_gd_final_kw:.0f} kWp"
        }

    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8001)