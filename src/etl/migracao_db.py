import os
import sys
import geopandas as gpd
import pandas as pd
from sqlalchemy import create_engine, text
import logging

# Setup de caminhos
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from config import PATH_GDB

# Configuração de Log
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger("MigracaoDB")

# Camadas do GridScope
CAMADAS_ALVO = {
    'UNTRMT': 'transformadores',
    'UCBT_tab': 'consumidores',   # Tabela pura
    'UGBT_tab': 'geracao_gd',     # Tabela pura
    'SUB': 'subestacoes',
    'SSDMT': 'rede_mt'
}

def get_database_engine():
    db_url = os.getenv("DATABASE_URL", "postgresql://admin:minhasenha@localhost:5432/gridscope_local")
    return create_engine(db_url)

def migrar_gdb_para_sql():
    if not os.path.exists(PATH_GDB):
        logger.error(f"GDB não encontrado em: {PATH_GDB}")
        return

    engine = get_database_engine()
    logger.info(f"🔌 Conectando ao Banco de Dados...")
    logger.info(f"📂 Lendo Fonte: {os.path.basename(PATH_GDB)}")

    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        logger.info("✅ Conexão OK!")
    except Exception as e:
        logger.error(f"❌ Falha ao conectar no Banco: {e}")
        return

    for layer_gdb, nome_tabela in CAMADAS_ALVO.items():
        logger.info(f"--------------------------------------------------")
        logger.info(f"🔄 Processando camada: {layer_gdb} -> Tabela: {nome_tabela}")
        
        try:
            # Leitura do arquivo
            gdf = gpd.read_file(PATH_GDB, layer=layer_gdb, engine='pyogrio')
            
            if gdf.empty:
                logger.warning(f"⚠️ Camada {layer_gdb} vazia.")
                continue

            # --- AQUI ESTÁ A CORREÇÃO BLINDADA ---
            # Verifica explicitamente se é um GeoDataFrame (Mapa) ou DataFrame (Tabela)
            e_mapa = isinstance(gdf, gpd.GeoDataFrame)

            if e_mapa:
                # É UM MAPA (Tem geometria válida)
                if gdf.crs and gdf.crs.to_string() != "EPSG:4326":
                    gdf = gdf.to_crs("EPSG:4326")
                
                logger.info(f"   🗺️  Salvando MAPA ({len(gdf)} registros)...")
                gdf.to_postgis(nome_tabela, engine, if_exists='replace', index=False, chunksize=5000)
            
            else:
                # É UMA TABELA (Não tem geometria ou é inválida)
                logger.info(f"   📄 Salvando TABELA ({len(gdf)} registros)...")
                
                # Remove coluna geometry se existir mas estiver vazia/nula (comum em CSVs/GDBs mistos)
                if 'geometry' in gdf.columns:
                    gdf = gdf.drop(columns=['geometry'])
                
                # Salva usando pandas to_sql normal
                gdf.to_sql(nome_tabela, engine, if_exists='replace', index=False, chunksize=10000)
            
            logger.info(f"✅ Sucesso!")

        except ValueError:
            logger.warning(f"⚠️ Camada {layer_gdb} não encontrada no arquivo.")
        except Exception as e:
            logger.error(f"❌ Erro crítico em {layer_gdb}: {e}")

    logger.info("🏁 MIGRACAO CONCLUÍDA COM SUCESSO 🏁")

if __name__ == "__main__":
    migrar_gdb_para_sql()