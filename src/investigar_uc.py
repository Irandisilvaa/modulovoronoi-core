import geopandas as gpd
import pandas as pd
import os
import sys

# Ajuste o nome se necessário
NOME_PASTA_GDB = "Energisa_SE_6587_2023-12-31_V11_20250701-0833.gdb"

def investigar():
    dir_atual = os.path.dirname(os.path.abspath(__file__))
    caminho_gdb = os.path.join(dir_atual, "..", "dados", NOME_PASTA_GDB)

    print("🕵️  INVESTIGAÇÃO DE DADOS DA ANEEL")
    print("-" * 40)

    # 1. TENTAR LER CONSUMIDORES (UCBT_tab)
    print("👉 Tentando ler Unidades Consumidoras (UCBT_tab)...")
    try:
        # Lemos como geodataframe para ver se tem geometria
        uc_gdf = gpd.read_file(caminho_gdb, layer='UCBT_tab', engine='pyogrio', rows=5)
        
        print(f"   Colunas encontradas: {uc_gdf.columns.tolist()}")
        if 'geometry' in uc_gdf.columns and uc_gdf.geometry.notnull().any():
            print("   ✅ BINGO! A tabela de consumidores TEM localização (mapa)!")
            tem_geo_uc = True
        else:
            print("   ⚠️  A tabela de consumidores NÃO tem geometria (apenas dados).")
            tem_geo_uc = False
            
        # Tenta ver se tem coluna de Classe (Residencial/Comercial)
        # Geralmente é: CLAS_SUB, CLASSE, SUB_CLAS
        print(f"   Exemplo de dados:\n{uc_gdf.head(2)}")
        
    except Exception as e:
        print(f"   ❌ Erro ao ler UCBT: {e}")

    print("-" * 40)

    # 2. TENTAR LER TRANSFORMADORES (UNTRMT)
    # Essa camada é quase garantido que tem geometria (Pontos no poste)
    print("👉 Tentando ler Transformadores (UNTRMT)...")
    try:
        trafo_gdf = gpd.read_file(caminho_gdb, layer='UNTRMT', engine='pyogrio', rows=5)
        
        print(f"   Colunas encontradas: {trafo_gdf.columns.tolist()}")
        if 'geometry' in trafo_gdf.columns:
            print("   ✅ Transformadores têm localização!")
        
        # Procurar colunas de Potência (KVA) ou Tipo
        # Geralmente: POT_NOM, TEN_SEC, etc.
        print(f"   Exemplo de dados:\n{trafo_gdf.head(2)}")
        
    except Exception as e:
        print(f"   ❌ Erro ao ler Transformadores: {e}")

if __name__ == "__main__":
    investigar()