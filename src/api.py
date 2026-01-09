from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel
import json
import os
import sys
import requests
import urllib.parse 
from datetime import datetime, date
from typing import Dict, Optional, List, Any
from shapely.geometry import mapping

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
try:
    from utils import carregar_dados_cache, fundir_dados_geo_mercado
    from cache_redis import cache_json
except ImportError as e:
    print(f"CRITICAL API ERROR: {e}")
    sys.exit(1)

app = FastAPI(
    title="GridScope API",
    description="API Avançada de Monitoramento de Rede",
    version="4.7" 
)

def limpar_float(valor):
    """Converte strings BR (1.000,00) ou sujas para float Python (1000.00)"""
    if isinstance(valor, (int, float)):
        return float(valor)
    if isinstance(valor, str):
        try:
            limpo = valor.replace("R$", "").replace(" ", "").replace(".", "").replace(",", ".")
            return float(limpo)
        except ValueError:
            return 0.0
    return 0.0

class MetricasRede(BaseModel):
    total_clientes: int
    consumo_anual_mwh: float
    nivel_criticidade_gd: str

class PerfilClasse(BaseModel):
    qtd_clientes: int
    pct: float
    consumo_anual_mwh: Optional[float] = 0.0 

class GeracaoDistribuida(BaseModel):
    total_unidades: int
    potencia_total_kw: float
    detalhe_por_classe: Dict[str, float]

class SubestacaoData(BaseModel):
    subestacao: str
    metricas_rede: MetricasRede
    geracao_distribuida: GeracaoDistribuida
    perfil_consumo: Dict[str, PerfilClasse]
    geometry: Optional[Dict[str, Any]] = None

class SimulacaoSolar(BaseModel):
    subestacao: str
    data_referencia: str
    fonte_dados: str
    condicao_tempo: str
    irradiacao_solar_kwh_m2: float
    temperatura_max_c: float
    fator_perda_termica: float
    potencia_instalada_kw: float
    geracao_estimada_mwh: float
    impacto_na_rede: str


def obter_clima_avancado(lat: float, lon: float, data_alvo: date):
    hoje = date.today()
    
    if data_alvo < hoje:
        url = "https://archive-api.open-meteo.com/v1/archive"
        fonte = "Historico Real"
    else:
        url = "https://api.open-meteo.com/v1/forecast"
        fonte = "Previsao Numerica"

    params = {
        "latitude": lat,
        "longitude": lon,
        "start_date": data_alvo.isoformat(),
        "end_date": data_alvo.isoformat(),
        "daily": ["shortwave_radiation_sum", "temperature_2m_max", "weather_code"],
        "timezone": "America/Sao_Paulo"
    }
    
    try:
        response = requests.get(url, params=params, timeout=5)
        response.raise_for_status()
        dados = response.json()
        
        daily = dados.get('daily', {})
        
        irradiacao_mj = daily['shortwave_radiation_sum'][0]
        if irradiacao_mj is None: irradiacao_mj = 0
        irradiacao_kwh = irradiacao_mj / 3.6
        
        temp_max = daily['temperature_2m_max'][0]
        if temp_max is None: temp_max = 30.0
        
        code = daily['weather_code'][0]
        tempo_desc = "Ceu Limpo"
        if code > 3: tempo_desc = "Nublado"
        if code > 50: tempo_desc = "Chuvoso"

        return irradiacao_kwh, temp_max, tempo_desc, fonte
        
    except Exception as e:
        print(f"Erro Clima: {e}")
        return 5.0, 30.0, "Dados Offline", "Estimativa Padrao"

@app.get("/", tags=["Status"])
def home():
    return {"status": "online", "system": "GridScope Core 4.7"}

@app.get("/mercado/ranking", response_model=List[SubestacaoData], tags=["Core"])
@cache_json(ttl_seconds=300)
def obter_dados_completos():
    try:
        gdf, dados_mercado = carregar_dados_cache()
        dados_fundidos = fundir_dados_geo_mercado(gdf, dados_mercado)
        
        for item in dados_fundidos:
            if item.get('geometry'):
                item['geometry'] = mapping(item['geometry'])
            
            if 'metricas_rede' in item:
                m = item['metricas_rede']
                if 'consumo_anual_mwh' in m:
                    m['consumo_anual_mwh'] = limpar_float(m['consumo_anual_mwh'])

            if 'perfil_consumo' in item:
                for classe, valores in item['perfil_consumo'].items():
                    raw_consumo = valores.get('consumo_anual_mwh', valores.get('consumo', 0))
                    valores['consumo_anual_mwh'] = limpar_float(raw_consumo)

        return dados_fundidos
    except Exception as e:
        print(f"Erro detalhado API: {e}") 
        raise HTTPException(status_code=500, detail=f"Erro interno: {str(e)}")

@app.get("/mercado/geojson", tags=["Core"])
@cache_json(ttl_seconds=3600)
def obter_apenas_geojson():
    """Retorna apenas o GeoJSON dos territórios Voronoi do banco PostgreSQL"""
    try:
        gdf, _ = carregar_dados_cache()
        return json.loads(gdf.to_json())
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro ao carregar GeoJSON: {str(e)}")

@app.get("/simulacao/{nome_subestacao}", response_model=SimulacaoSolar, tags=["Simulacao"])
def simular_geracao(
    nome_subestacao: str, 
    data: Optional[str] = Query(None, description="Data: DD-MM-AAAA ou DD/MM/AAAA")
):
    data_obj = date.today()
    if data:
        data_clean = data.replace("/", "-").replace(" ", "-")
        formatos = ["%Y-%m-%d", "%d-%m-%Y"]
        parsed = False
        for fmt in formatos:
            try:
                data_obj = datetime.strptime(data_clean, fmt).date()
                parsed = True
                break
            except ValueError:
                continue
        if not parsed:
            raise HTTPException(status_code=400, detail="Formato invalido. Use DD-MM-AAAA")

    try:
        gdf, dados_mercado = carregar_dados_cache()
        dados_fundidos = fundir_dados_geo_mercado(gdf, dados_mercado)
    
        nome_buscado = urllib.parse.unquote(nome_subestacao).strip().upper()
        print(f"DEBUG: Buscando por '{nome_buscado}'...")

        alvo = None
        for x in dados_fundidos:
            nome_banco = str(x['subestacao']).strip().upper()
            
            if nome_banco == nome_buscado:
                alvo = x; break
            if nome_buscado in nome_banco:
                alvo = x; break
            if nome_banco in nome_buscado:
                alvo = x; break

        if not alvo: 
            print(f"ERRO: '{nome_buscado}' nao encontrado no cache.")
            raise HTTPException(status_code=404, detail=f"Subestacao '{nome_buscado}' nao encontrada")

    except HTTPException as he:
        raise he
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro dados: {e}")

    lat, lon = -10.9472, -37.0731
    try:
        geom = alvo.get('geometry')
        if isinstance(geom, dict) and 'coordinates' in geom:
            coords = geom['coordinates']
            if isinstance(coords[0], float):
                lon, lat = coords[0], coords[1]
            else: 
                lon, lat = coords[0][0][0], coords[0][0][1]
    except Exception as e:
        print(f"Aviso Geometria: {e}")

    irradiacao, temp_max, desc_tempo, fonte = obter_clima_avancado(lat, lon, data_obj)
    
    perda_termica = 0.0
    if temp_max > 25:
        delta_t = temp_max - 25
        perda_termica = delta_t * 0.004
    
    fator_performance_base = 0.75
    fator_performance_real = fator_performance_base * (1 - perda_termica)
    
    potencia = limpar_float(alvo['geracao_distribuida']['potencia_total_kw'])
    
    geracao_kwh = potencia * irradiacao * fator_performance_real
    geracao_mwh = geracao_kwh / 1000

    impacto = "Normal"
    if irradiacao > 5.5 and temp_max < 30:
        impacto = "CRITICO: Sol forte e Temp amena. Pico de injecao!"
    elif irradiacao > 5.0:
        impacto = "ALTA INJECAO: Atencao ao fluxo reverso."
    elif irradiacao < 2.0:
        impacto = "BAIXA GERACAO: Rede suportara carga maxima."
    
    return {
        "subestacao": alvo['subestacao'],
        "data_referencia": data_obj.strftime("%d/%m/%Y"),
        "fonte_dados": fonte,
        "condicao_tempo": desc_tempo,
        "irradiacao_solar_kwh_m2": round(irradiacao, 2),
        "temperatura_max_c": round(temp_max, 1),
        "fator_perda_termica": round(perda_termica * 100, 2),
        "potencia_instalada_kw": potencia,
        "geracao_estimada_mwh": round(geracao_mwh, 2),
        "impacto_na_rede": impacto
    }