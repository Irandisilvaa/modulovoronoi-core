import geopandas as gpd
import os
import sys

NOME_PASTA_GDB = "Energisa_SE_6587_2023-12-31_V11_20250701-0833.gdb"

def carregar_subestacoes():
    print("Iniciando módulo de carregamento (ETL)...")

    caminho_deste_arquivo = os.path.abspath(__file__)
    pasta_etl = os.path.dirname(caminho_deste_arquivo)
    pasta_src = os.path.dirname(pasta_etl)
    pasta_raiz = os.path.dirname(pasta_src)
    caminho_gdb = os.path.join(pasta_raiz, "dados", NOME_PASTA_GDB)
    print(f"Caminho calculado: {caminho_gdb}")
    
    if not os.path.exists(caminho_gdb):
        print(f"ERRO CRÍTICO: Pasta de dados não encontrada!")
        print(f"O sistema esperava encontrar em: {caminho_gdb}")
        print("DICA: Verifique se o nome da pasta .gdb dentro de 'dados' está exatamente igual ao nome no código.")
        sys.exit(1)
    print(f"Arquivo encontrado! Lendo GDB...")
    
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