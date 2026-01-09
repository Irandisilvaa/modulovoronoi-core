"""
Módulo para carregar dados de subestações do PostgreSQL
"""
import geopandas as gpd
import pandas as pd
import os
import sys

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

def carregar_subestacoes():
    """
    Carrega subestações do PostgreSQL (sem fallback para GDB)
    """
    from database import carregar_subestacoes as db_carregar_subs
    
    print("📥 Carregando subestações do PostgreSQL...")
    gdf = db_carregar_subs()
    
    if 'COD_ID' in gdf.columns:
        gdf['COD_ID'] = gdf['COD_ID'].astype(str)
    
    print(f"✅ {len(gdf)} subestações carregadas do banco")
    return gdf