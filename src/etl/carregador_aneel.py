import geopandas as gpd
import os
import sys

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import PATH_GDB

def carregar_subestacoes():
    print("Iniciando módulo de carregamento (ETL)...")
    print(f"Lendo GDB em: {PATH_GDB}")

    
    if not os.path.exists(PATH_GDB):
        print(f"ERRO CRÍTICO: Pasta de dados não encontrada!")
        print(f"O sistema esperava encontrar em: {PATH_GDB}")
        sys.exit(1)

    
    try:
        gdf = gpd.read_file(PATH_GDB, layer='SUB', engine='pyogrio')
        coluna_nome = 'NOM'
        if 'NOM' not in gdf.columns:
            possiveis = ['NOME', 'Nom', 'DS_NOME', 'NO_SUB']
            for p in possiveis:
                if p in gdf.columns:
                    coluna_nome = p
                    break
        
        if coluna_nome not in gdf.columns:
            print(f"ERRO: Colunas encontradas: {gdf.columns.tolist()}")
            print("Não achei a coluna de Nome da Subestação.")
            sys.exit(1)

        gdf = gdf.rename(columns={coluna_nome: 'NOM'})

        cols_finais = ['COD_ID', 'NOM', 'geometry']
        if 'COD_ID' not in gdf.columns and 'ID' in gdf.columns:
            gdf = gdf.rename(columns={'ID': 'COD_ID'})

        cols_existentes = [c for c in cols_finais if c in gdf.columns]
        gdf_limpo = gdf[cols_existentes].copy()
        gdf_limpo = gdf_limpo.dropna(subset=['NOM'])
        
        print(f"Sucesso! {len(gdf_limpo)} subestações carregadas.")
        return gdf_limpo

    except Exception as e:
        print(f"Erro técnico ao ler o GDB: {e}")
        sys.exit(1)

if __name__ == "__main__":
    carregar_subestacoes()