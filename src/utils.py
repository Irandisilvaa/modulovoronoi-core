import json
import os
import geopandas as gpd
import pandas as pd
import sys
import math 



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
    """
    Carrega dados do PostgreSQL (100% Database - Sem arquivos).
    Retorna: (GeoDataFrame, List[Dict])
    """
    try:
        sys.path.append(os.path.dirname(os.path.abspath(__file__)))
        from database import carregar_voronoi, carregar_subestacoes, carregar_cache_mercado
        
        # 1. Voronoi + Nomes (Geometry Source)
        gdf = carregar_voronoi()
        
        # Enriquecer com nomes oficiais da tabela subestacoes
        gdf_subs = carregar_subestacoes()
        if 'NOME' in gdf_subs.columns and 'COD_ID' in gdf_subs.columns:
            # Cria mapa COD_ID -> NOME
            gdf_subs_simple = gdf_subs[['COD_ID', 'NOME']].drop_duplicates(subset=['COD_ID']).copy()
            gdf_subs_simple['COD_ID'] = gdf_subs_simple['COD_ID'].astype(str)
            
            # Garante join por string
            gdf['COD_ID'] = gdf['COD_ID'].astype(str)
            gdf = gdf.merge(gdf_subs_simple, on='COD_ID', how='left')
            
            # Renomeia para padrão esperado pelo frontend (NOM)
            gdf = gdf.rename(columns={'NOME': 'NOM'})
        
        # 2. Dados de Mercado (Business Data Source)
        dados_mercado = carregar_cache_mercado()
        
        return gdf, dados_mercado
        
    except ImportError as ie:
        raise Exception(f"Erro de Importação (database.py não achado): {ie}")
    except Exception as e:
        print(f"❌ Erro ao carregar dados do Banco: {e}")
        return None, []

def fundir_dados_geo_mercado(gdf, dados_mercado):
    """Cruza dados."""
    geo_map = {
        str(row['NOM']).strip().upper(): row['geometry']
        for _, row in gdf.iterrows()
        if pd.notnull(row['NOM'])
    }
    dados_finais = []
    lista = dados_mercado if isinstance(dados_mercado, list) else dados_mercado.to_dict('records')

    for item in lista:
        sub_nome = str(item.get('subestacao', '')).split(' (ID')[0].strip().upper()
        item['geometry'] = geo_map.get(sub_nome)
        dados_finais.append(item)
        
    return dados_finais
