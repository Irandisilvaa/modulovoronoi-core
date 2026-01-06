import json
import os
import geopandas as gpd
import pandas as pd
import sys

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

try:
    from config import PATH_GEOJSON, PATH_JSON_MERCADO
except ImportError:
    PATH_GEOJSON = "dados/subestacoes.geojson"
    PATH_JSON_MERCADO = "dados/mercado.json"

def limpar_float(val):
    """
    Função auxiliar para converter valores numéricos (string ou float)
    para float padrão Python. Trata formatos brasileiros (1.000,00).
    Necessária para os cálculos na interface.
    """
    if val is None or val == "":
        return 0.0
    
    if isinstance(val, (int, float)):
        return float(val)
    val_str = str(val).strip()
    
    try:
        if ',' in val_str and '.' in val_str:
            val_str = val_str.replace('.', '').replace(',', '.')
        elif ',' in val_str:
            val_str = val_str.replace(',', '.')
            
        return float(val_str)
    except ValueError:
        return 0.0

def carregar_dados_cache():
    """
    Carrega os dados do GeoJSON e do JSON de mercado.
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
    Adiciona a geometria ao objeto JSON para uso na API ou Visualização.
    """
    geo_map = {
        str(row['NOM']).strip().upper(): row['geometry'] 
        for _, row in gdf.iterrows() 
        if pd.notnull(row['NOM'])
    }

    dados_finais = []
    
    lista_iteravel = dados_mercado if isinstance(dados_mercado, list) else dados_mercado.to_dict('records')

    for item in lista_iteravel:
        sub_nome = str(item.get('subestacao', '')).split(' (ID')[0].strip().upper()
        
        item['geometry'] = geo_map.get(sub_nome)
        
        dados_finais.append(item)
        
    return dados_finais