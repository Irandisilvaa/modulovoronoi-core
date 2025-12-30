import geopandas as gpd
import os
import sys

NOME_PASTA_GDB = "Energisa_SE_6587_2023-12-31_V11_20250701-0833.gdb"

def carregar_subestacoes():
    dir_atual = os.path.dirname(os.path.abspath(__file__))
    caminho_gdb = os.path.join(dir_atual, "..", "..", "dados", NOME_PASTA_GDB)
    
    if not os.path.exists(caminho_gdb):
        print(f"ERRO CRÍTICO: Pasta de dados não encontrada!")
        print(f"O sistema procurou em: {caminho_gdb}")
        sys.exit(1)

    print(f"Lendo GDB: {NOME_PASTA_GDB} ...")
    try:
        gdf = gpd.read_file(caminho_gdb, layer='SUB', engine='pyogrio')
        coluna_nome = 'NOM'
        if 'NOM' not in gdf.columns:
            possiveis = ['NOME', 'Nom', 'DS_NOME', 'NO_SUB']
            for p in possiveis:
                if p in gdf.columns:
                    coluna_nome = p
                    break
        if coluna_nome not in gdf.columns:
            print("ERRO: Não achei a coluna de Nome da Subestação.")
            sys.exit(1)
        gdf = gdf.rename(columns={coluna_nome: 'NOM'})
        cols_finais = ['COD_ID', 'NOM', 'geometry']
      
        if 'COD_ID' not in gdf.columns and 'ID' in gdf.columns:
             gdf = gdf.rename(columns={'ID': 'COD_ID'})

        cols_existentes = [c for c in cols_finais if c in gdf.columns]
        gdf_limpo = gdf[cols_existentes]
        
        gdf_limpo = gdf_limpo.dropna(subset=['NOM'])
     
        print(f"Sucesso! {len(gdf_limpo)} subestações carregadas via módulo ETL.")
        return gdf_limpo
    
    except Exception as e:
        print(f"Erro ao ler o GDB: {e}")
        sys.exit(1)

if __name__ == "__main__":
    carregar_subestacoes()