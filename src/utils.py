import json
import os
import geopandas as gpd
import pandas as pd
import sys

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from config import PATH_GEOJSON, PATH_JSON_MERCADO

def carregar_dados_cache():
    """
    Carrega o GeoJSON (mapa) e o JSON (dados de mercado) de forma unificada.
    Retorna: (GeoDataFrame, List[Dict])
    """
    if not os.path.exists(PATH_GEOJSON):
        raise FileNotFoundError(f"GeoJSON não encontrado em: {PATH_GEOJSON}")
    
    if not os.path.exists(PATH_JSON_MERCADO):
        raise FileNotFoundError(f"JSON de Mercado não encontrado em: {PATH_JSON_MERCADO}")

    try:
        gdf = gpd.read_file(PATH_GEOJSON)
        
        with open(PATH_JSON_MERCADO, 'r', encoding='utf-8') as f:
            dados_mercado = json.load(f)

        return gdf, dados_mercado
    except Exception as e:
        raise Exception(f"Erro ao ler arquivos de cache: {str(e)}")

def fundir_dados_geo_mercado(gdf, dados_mercado):
    """
    Cruza os dados do mapa (gdf) com os dados estatísticos (dados_mercado).
    Adiciona a geometria ao objeto JSON para uso na API.
    """
    geo_map = {
        row['NOM']: row['geometry'] 
        for _, row in gdf.iterrows() 
        if pd.notnull(row['NOM'])
    }

    dados_finais = []
    for item in dados_mercado:
        sub_nome = item['subestacao']
        item['geometry'] = geo_map.get(sub_nome)
        
        dados_finais.append(item)
        
    return dados_finais