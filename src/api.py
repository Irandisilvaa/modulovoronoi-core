from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from typing import List, Optional
import json
import os

# Metadados da API (Isso aparece na documentação automática)
tags_metadata = [
    {"name": "Geografia", "description": "Dados espaciais para sistemas GIS e Mapas."},
    {"name": "Comercial", "description": "Dados de mercado, clientes e consumo."},
    {"name": "Integração", "description": "Endpoints otimizados para sistemas externos (SCADA/ADMS)."},
]

app = FastAPI(
    title="GridScope Core API",
    description="Motor de Inteligência Geospacial para Distribuição de Energia.",
    version="1.0.0",
    openapi_tags=tags_metadata
)

# --- CONFIGURAÇÃO DE CORS ---
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- CARREGAMENTO DE DADOS (CACHE) ---
def carregar_dados():
    dir_atual = os.path.dirname(os.path.abspath(__file__))
    dir_raiz = os.path.dirname(dir_atual)
    
    caminho_geo = os.path.join(dir_raiz, "subestacoes_logicas_aracaju.geojson")
    caminho_json = os.path.join(dir_raiz, "perfil_mercado_aracaju.json")

    # Carrega GeoJSON
    with open(caminho_geo, 'r', encoding='utf-8') as f:
        geo_data = json.load(f)
        
    # Carrega Dados de Mercado
    with open(caminho_json, 'r', encoding='utf-8') as f:
        mercado_data = json.load(f)
        
    return geo_data, mercado_data

# Carrega na inicialização
GEO_DATA, MERCADO_DATA = carregar_dados()

# --- ROTAS (ENDPOINTS) ---

@app.get("/", include_in_schema=False)
def health_check():
    return {"status": "active", "system": "GridScope API", "version": "1.0.0"}

# --- 1. MÓDULO GEOGRÁFICO (Para o Frontend de Mapa) ---
@app.get("/geo/zonas", tags=["Geografia"])
def obter_poligonos_voronoi():
    """
    Retorna o GeoJSON completo das áreas de influência.
    Padrão RFC 7946 para compatibilidade com Mapbox, Leaflet e ArcGIS.
    """
    return GEO_DATA

# --- 2. MÓDULO COMERCIAL (Para Dashboards) ---
@app.get("/comercial/subestacoes", tags=["Comercial"])
def listar_subestacoes():
    """Lista todas as subestações disponíveis no sistema."""
    nomes = [item['subestacao'] for item in MERCADO_DATA]
    return {"total": len(nomes), "subestacoes": sorted(nomes)}

@app.get("/comercial/detalhes/{nome_subestacao}", tags=["Comercial"])
def obter_kpis_subestacao(nome_subestacao: str):
    """
    Retorna perfil de consumo, quantidade de clientes e carga total.
    """
    dados = next((item for item in MERCADO_DATA if item["subestacao"] == nome_subestacao), None)
    if dados:
        return dados
    raise HTTPException(status_code=404, detail="Subestação não encontrada")

# --- 3. MÓDULO DE INTEGRAÇÃO (O Pulo do Gato 🐱) ---
@app.get("/integracao/clientes-criticos", tags=["Integração"])
def buscar_clientes_criticos(tipo: str = Query("Industrial", enum=["Industrial", "Comercial", "Residencial"])):
    """
    **Endpoint para Sistemas Externos.**
    Permite que o sistema de despacho consulte onde estão concentrados os clientes críticos (ex: Indústrias).
    Retorna lista ordenada por quantidade de clientes críticos.
    """
    ranking = []
    for item in MERCADO_DATA:
        qtd = item['perfil'].get(tipo, {}).get('qtd', 0)
        if qtd > 0:
            ranking.append({
                "subestacao": item['subestacao'],
                "tipo_cliente": tipo,
                "quantidade": qtd,
                "impacto_rede": "Alto" if qtd > 10 else "Médio"
            })
    
    # Ordena do maior para o menor
    ranking_ordenado = sorted(ranking, key=lambda x: x['quantidade'], reverse=True)
    return ranking_ordenado