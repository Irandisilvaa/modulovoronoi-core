import geopandas as gpd
import os
import sys

# Ajusta o caminho para encontrar o config.py na raiz
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    from config import PATH_GDB
except ImportError:
    # Fallback caso não ache o config
    PATH_GDB = "caminho/para/seu/arquivo.gdb" 

def carregar_subestacoes():
    print("Iniciando módulo de carregamento (ETL)...")
    print(f"Lendo GDB em: {PATH_GDB}")

    if not os.path.exists(PATH_GDB):
        print(f"ERRO CRÍTICO: Pasta de dados não encontrada!")
        print(f"O sistema esperava encontrar em: {PATH_GDB}")
        sys.exit(1)

    try:
        # 1. Carrega Subestações (Mapa)
        # engine='pyogrio' é muito mais rápido para GDBs grandes
        gdf = gpd.read_file(PATH_GDB, layer='SUB', engine='pyogrio')
        
        # 2. Normaliza Nome
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

        # 3. Normaliza ID (Essencial para cruzar com os clientes)
        # Se chamar 'ID', renomeia para 'COD_ID'
        if 'COD_ID' not in gdf.columns and 'ID' in gdf.columns:
            gdf = gdf.rename(columns={'ID': 'COD_ID'})

        # Garante que o COD_ID seja string para evitar erro de comparação com a tabela de clientes
        if 'COD_ID' in gdf.columns:
            gdf['COD_ID'] = gdf['COD_ID'].astype(str)

        # --- MODIFICAÇÃO: FILTRO DE CARGA (CLIENTES REAIS) ---
        print("Cruzando com base de consumidores para validar operação...")
        
        try:
            # Descobre o nome da tabela de consumidores (UCBT ou UCBT_tab)
            layers = gpd.list_layers(PATH_GDB)
            layer_uc = next((l for l in ['UCBT_tab', 'UCBT'] if l in layers['name'].values), None)
            
            if layer_uc:
                # Lê apenas a coluna 'SUB' da tabela de consumidores (Super rápido)
                df_clientes = gpd.read_file(
                    PATH_GDB, 
                    layer=layer_uc, 
                    engine='pyogrio', 
                    ignore_geometry=True, 
                    columns=['SUB']
                )
                
                # Lista de IDs de subestações que realmente têm contas de luz ativas
                # Converte para string para garantir o match com o gdf
                ids_com_carga = df_clientes['SUB'].astype(str).unique()
                
                total_antes = len(gdf)
                
                # O FILTRO: Mantém apenas se o ID da subestação estiver na lista de clientes
                gdf = gdf[gdf['COD_ID'].isin(ids_com_carga)].copy()
                
                removidas = total_antes - len(gdf)
                print(f"♻️  Limpeza: {removidas} subestações sem clientes (Planejadas/Sem Carga) removidas.")
            else:
                print("⚠️  Aviso: Tabela UCBT não encontrada. Filtro de carga não aplicado.")
                
        except Exception as e_filtro:
            print(f"⚠️  Erro no filtro de clientes: {e_filtro}. Mantendo dados originais.")
        # -----------------------------------------------------

        # 4. Seleção Final de Colunas
        cols_finais = ['COD_ID', 'NOM', 'geometry']
        cols_existentes = [c for c in cols_finais if c in gdf.columns]
        gdf_limpo = gdf[cols_existentes].copy()
        
        # Remove nomes vazios
        gdf_limpo = gdf_limpo.dropna(subset=['NOM'])
        
        print(f"Sucesso! {len(gdf_limpo)} subestações COM CARGA carregadas.")
        return gdf_limpo

    except Exception as e:
        print(f"Erro técnico ao ler o GDB: {e}")
        sys.exit(1)

if __name__ == "__main__":
    carregar_subestacoes()