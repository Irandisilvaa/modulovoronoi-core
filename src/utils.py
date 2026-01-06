import json
import os
import geopandas as gpd
import pandas as pd
import sys

# Define nomes de arquivo que você está usando (baseado no seu erro)
FILENAME_GEOJSON = "subestacoes_logicas_aracaju.geojson"
FILENAME_JSON = "mercado.json" # Ou o nome exato do seu json de mercado

def encontrar_arquivo(nome_arquivo):
    """
    Procura o arquivo recursivamente a partir da raiz do projeto.
    Retorna o caminho absoluto se encontrar.
    """
    # 1. Tenta achar a raiz do projeto (subindo de src/utils.py para raiz)
    current_dir = os.path.dirname(os.path.abspath(__file__)) # Pasta src
    project_root = os.path.dirname(current_dir) # Pasta raiz (gridscope-core)
    
    # Lista de locais prováveis para buscar
    caminhos_tentativa = [
        os.path.join(project_root, "dados", nome_arquivo), # Pasta dados/
        os.path.join(project_root, nome_arquivo),          # Raiz do projeto
        os.path.join(current_dir, nome_arquivo),           # Pasta src/
        nome_arquivo                                       # Caminho relativo simples
    ]
    
    for caminho in caminhos_tentativa:
        if os.path.exists(caminho):
            return caminho
            
    return None

def limpar_float(val):
    """Converte valores numéricos para float (trata vírgula BR)."""
    if val is None or val == "": return 0.0
    if isinstance(val, (int, float)): return float(val)
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
    """Carrega dados geoespaciais e de mercado de forma resiliente."""
    
    # 1. Encontrar GeoJSON
    path_geo = encontrar_arquivo(FILENAME_GEOJSON)
    if not path_geo:
        # Tenta um nome genérico caso o específico falhe
        path_geo = encontrar_arquivo("subestacoes.geojson")
        
    if not path_geo:
        raise FileNotFoundError(
            f"❌ ERRO CRÍTICO: O arquivo '{FILENAME_GEOJSON}' não foi encontrado na pasta 'dados/' nem na raiz."
        )

    # 2. Encontrar JSON de Mercado
    path_mercado = encontrar_arquivo(FILENAME_JSON)
    if not path_mercado:
        # Tenta achar json com nome parecido
        path_mercado = encontrar_arquivo("perfil_mercado_aracaju.json")

    if not path_mercado:
        raise FileNotFoundError(f"❌ ERRO CRÍTICO: JSON de mercado não encontrado.")

    try:
        # Carrega os arquivos
        gdf = gpd.read_file(path_geo)
        
        with open(path_mercado, 'r', encoding='utf-8') as f:
            dados_mercado = json.load(f)

        return gdf, dados_mercado
        
    except Exception as e:
        raise Exception(f"Erro ao ler arquivos ({path_geo}): {str(e)}")

def fundir_dados_geo_mercado(gdf, dados_mercado):
    """Cruza dados."""
    geo_map = {str(row['NOM']).strip().upper(): row['geometry'] for _, row in gdf.iterrows() if pd.notnull(row['NOM'])}
    dados_finais = []
    lista = dados_mercado if isinstance(dados_mercado, list) else dados_mercado.to_dict('records')

    for item in lista:
        sub_nome = str(item.get('subestacao', '')).split(' (ID')[0].strip().upper()
        item['geometry'] = geo_map.get(sub_nome)
        dados_finais.append(item)
        
    return dados_finais