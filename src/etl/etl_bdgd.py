import geopandas as gpd
import os
import sys

# --- CONFIGURAÇÃO ---
# Verifique se o nome bate com a pasta dentro de 'dados'
NOME_PASTA_GDB = "Energisa_SE_6587_2023-12-31_V11_20250701-0833.gdb"

def carregar_subestacoes():
    """
    Lê o arquivo GDB da Energisa e retorna um GeoDataFrame limpo.
    """
    # Pega o diretório onde ESTE arquivo está (src/etl)
    dir_atual = os.path.dirname(os.path.abspath(__file__))
    
    # --- CORREÇÃO AQUI ---
    # Antes era: "..", "dados" (Voltava 1 nível)
    # Agora é: "..", "..", "dados" (Volta 2 níveis: sai de etl, sai de src, entra em dados)
    caminho_gdb = os.path.join(dir_atual, "..", "..", "dados", NOME_PASTA_GDB)
    
    if not os.path.exists(caminho_gdb):
        print(f"❌ ERRO CRÍTICO: Pasta de dados não encontrada!")
        print(f"O sistema procurou em: {caminho_gdb}")
        sys.exit(1)

    print(f"📂 Lendo GDB: {NOME_PASTA_GDB} ...")
    
    try:
        # Usa pyogrio para ser rápido
        gdf = gpd.read_file(caminho_gdb, layer='SUB', engine='pyogrio')
        
        # --- DEBUG: MOSTRAR COLUNAS REAIS ---
        # print(f"Colunas encontradas: {gdf.columns.tolist()}")
        
        # Tenta adivinhar o nome da coluna de Nome se 'NOM' não existir
        coluna_nome = 'NOM'
        if 'NOM' not in gdf.columns:
            # Tenta variações comuns
            possiveis = ['NOME', 'Nom', 'DS_NOME', 'NO_SUB']
            for p in possiveis:
                if p in gdf.columns:
                    coluna_nome = p
                    break
        
        # Se mesmo assim não achar, avisa e para
        if coluna_nome not in gdf.columns:
            print("❌ ERRO: Não achei a coluna de Nome da Subestação.")
            sys.exit(1)

        # Padronizar para o nosso código (renomear para NOM)
        gdf = gdf.rename(columns={coluna_nome: 'NOM'})

        # Selecionar apenas o necessário
        cols_finais = ['COD_ID', 'NOM', 'geometry']
        # Adiciona COD_ID se não existir (às vezes é ID)
        if 'COD_ID' not in gdf.columns and 'ID' in gdf.columns:
             gdf = gdf.rename(columns={'ID': 'COD_ID'})

        # Filtra colunas que realmente existem
        cols_existentes = [c for c in cols_finais if c in gdf.columns]
        gdf_limpo = gdf[cols_existentes]
        
        gdf_limpo = gdf_limpo.dropna(subset=['NOM'])
        
        print(f"✅ Sucesso! {len(gdf_limpo)} subestações carregadas via módulo ETL.")
        return gdf_limpo

    except Exception as e:
        print(f"❌ Erro ao ler o GDB: {e}")
        sys.exit(1)

if __name__ == "__main__":
    carregar_subestacoes()