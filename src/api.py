from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import json
import os
import requests
from datetime import datetime
from typing import Dict, Optional, List, Any

app = FastAPI(
    title="GridScope API",
    description="API de Inteligencia Geoespacial da Energisa (Dados + Geometria + Clima Tempo Real)",
    version="3.2"
)

# --- MODELOS DE DADOS (SCHEMAS) ---

class MetricasRede(BaseModel):
    total_clientes: int
    consumo_anual_mwh: float
    nivel_criticidade_gd: str

class PerfilClasse(BaseModel):
    qtd_clientes: int
    pct: float

class GeracaoDistribuida(BaseModel):
    total_unidades: int
    potencia_total_kw: float
    detalhe_por_classe: Dict[str, float]

# Modelo Principal que junta TUDO
class SubestacaoData(BaseModel):
    subestacao: str
    metricas_rede: MetricasRede
    geracao_distribuida: GeracaoDistribuida
    perfil_consumo: Dict[str, PerfilClasse]
    geometry: Optional[Dict[str, Any]] = None

# --- NOVO MODELO: SIMULACAO SOLAR ---
class SimulacaoSolar(BaseModel):
    subestacao: str
    data_hoje: str
    condicao_tempo: str
    irradiacao_solar_kwh_m2: float
    potencia_instalada_kw: float
    geracao_estimada_hoje_mwh: float
    impacto_na_rede: str

# --- FUNCOES AUXILIARES ---

def carregar_dados_completos():
    """Lê o JSON de estatisticas e funde com o GeoJSON de coordenadas."""
    
    # 1. Definir caminhos
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    path_stats = os.path.join(base_dir, "perfil_mercado_aracaju.json")
    path_geo = os.path.join(base_dir, "subestacoes_logicas_aracaju.geojson")
    
    # Validação
    if not os.path.exists(path_stats):
        raise FileNotFoundError("Estatisticas nao encontradas. Rode o script de analise.")
    if not os.path.exists(path_geo):
        raise FileNotFoundError("Arquivo GeoJSON (mapa) nao encontrado.")

    # 2. Carregar arquivos
    with open(path_stats, 'r', encoding='utf-8') as f:
        stats_list = json.load(f)
    
    with open(path_geo, 'r', encoding='utf-8') as f:
        geo_data = json.load(f)

    # 3. Criar mapa de geometrias para busca rapida
    geo_map = {}
    for feature in geo_data['features']:
        nome = feature['properties'].get('NOM')
        if nome:
            geo_map[nome] = feature['geometry']

    # 4. Injetar a geometria dentro do objeto de estatistica
    dados_finais = []
    for item in stats_list:
        sub_nome = item['subestacao']
        if sub_nome in geo_map:
            item['geometry'] = geo_map[sub_nome]
        else:
            item['geometry'] = None
        
        dados_finais.append(item)
            
    return dados_finais

def obter_clima_solar(lat: float, lon: float):
    """Consulta a API Open-Meteo para pegar a irradiação solar diaria."""
    url = "https://api.open-meteo.com/v1/forecast"
    params = {
        "latitude": lat,
        "longitude": lon,
        "daily": ["shortwave_radiation_sum", "weather_code"],
        "timezone": "America/Sao_Paulo",
        "forecast_days": 1
    }
    
    try:
        response = requests.get(url, params=params, timeout=5)
        response.raise_for_status()
        dados = response.json()
        
        irradiacao_mj = dados['daily']['shortwave_radiation_sum'][0]
        codigo_tempo = dados['daily']['weather_code'][0]
        
        if irradiacao_mj is None: irradiacao_mj = 0
        irradiacao_kwh = irradiacao_mj / 3.6
        
        descricao_tempo = "Céu Limpo ☀️"
        if codigo_tempo > 3: descricao_tempo = "Nublado ☁️"
        if codigo_tempo > 50: descricao_tempo = "Chuvoso 🌧️"
        if codigo_tempo > 95: descricao_tempo = "Tempestade ⛈️"
        
        return irradiacao_kwh, descricao_tempo
        
    except Exception as e:
        print(f"Erro na API de Clima: {e}")
        return 4.5, "Dados Offline (Histórico)"
# --- ENDPOINTS DA API ---

@app.get("/", tags=["Status"])
def home():
    return {
        "status": "online", 
        "system": "GridScope Core",
        "capabilities": ["Analytics", "GeoSpatial", "Energy-Fraud-Detection", "Real-Time-Weather"]
    }

@app.get("/mercado/ranking", response_model=List[SubestacaoData], tags=["Mercado & Geo"])
def obter_dados_completos():
    try:
        dados = carregar_dados_completos()
        return dados
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro interno: {str(e)}")

@app.get("/mercado/geojson", tags=["Geo"])
def obter_apenas_geojson():
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    path_geo = os.path.join(base_dir, "subestacoes_logicas_aracaju.geojson")
    
    if os.path.exists(path_geo):
        with open(path_geo, 'r', encoding='utf-8') as f:
            return json.load(f)
    raise HTTPException(status_code=404, detail="GeoJSON nao encontrado")

@app.get("/simulacao/{nome_subestacao}", response_model=SimulacaoSolar, tags=["Simulação Tempo Real"])
def simular_geracao_hoje(nome_subestacao: str):
    """
    Calcula a 'Usina Virtual' (VPP) usando dados reais de clima.
    Converte automaticamente o nome da subestação para MAIÚSCULO.
    """
 
    # Força tudo para maiusculo para bater com o JSON (ex: subesta7 -> SUBESTA7)
    nome_sub_tratado = nome_subestacao.upper()
   

    # 1. Carregar dados internos
    try:
        todos_dados = carregar_dados_completos()
    except Exception as e:
        raise HTTPException(status_code=500, detail="Erro ao carregar base de dados interna")

    # 2. Encontrar a subestação (Usando o nome tratado)
    alvo = next((x for x in todos_dados if x['subestacao'] == nome_sub_tratado), None)
    
    if not alvo:
        raise HTTPException(status_code=404, detail=f"Subestação '{nome_sub_tratado}' não encontrada")
    
    # 3. Pegar coordenadas
    lat_local, lon_local = -10.9472, -37.0731 # Default
    try:
        if alvo.get('geometry') and alvo['geometry'].get('coordinates'):
            coords = alvo['geometry']['coordinates'][0][0]
            lon_local = coords[0]
            lat_local = coords[1]
    except:
        pass

    # 4. Consultar API Externa
    irradiacao, tempo_desc = obter_clima_solar(lat_local, lon_local)
    
    # 5. Calcular a Geração
    potencia_total = alvo['geracao_distribuida']['potencia_total_kw']
    geracao_estimada_kwh = potencia_total * irradiacao * 0.75
    geracao_estimada_mwh = geracao_estimada_kwh / 1000
    
    # 6. Analise de Impacto
    impacto = "Normal"
    if irradiacao > 5.5:
        impacto = "ALTA INJEÇÃO: Possível fluxo reverso no horário de pico (12h)."
    elif irradiacao < 2.0:
        impacto = "BAIXA GERAÇÃO: Carga da rede será máxima hoje."
    else:
        impacto = "OPERAÇÃO NOMINAL: Geração dentro do esperado."

    return {
        "subestacao": nome_sub_tratado,
        "data_hoje": datetime.now().strftime("%d/%m/%Y"),
        "condicao_tempo": tempo_desc,
        "irradiacao_solar_kwh_m2": round(irradiacao, 2),
        "potencia_instalada_kw": potencia_total,
        "geracao_estimada_hoje_mwh": round(geracao_estimada_mwh, 2),
        "impacto_na_rede": impacto
    }