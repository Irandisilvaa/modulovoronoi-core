import os
import sys
import geopandas as gpd
import pandas as pd
from sqlalchemy import create_engine, text
import logging


sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

NOME_GDB = os.getenv("FILE_GDB", "Energisa_SE_6587_2024-12-31_V11_20250902-1412.gdb")
DIR_DADOS = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "dados")
PATH_GDB = os.path.join(DIR_DADOS, NOME_GDB)

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger("MigracaoDB")

CAMADAS_ALVO = {
    'UNTRMT': 'transformadores',
    'UCBT_tab': 'consumidores',
    'UGBT_tab': 'geracao_gd',
    'SUB': 'subestacoes',
    'SSDMT': 'rede_mt'
}

def get_database_engine():
    db_url = os.getenv("DATABASE_URL", "postgresql://postgres:1234@localhost:5433/gridscope_local")
    return create_engine(db_url)


def limpar_dados_antigos(engine):
    """
    Remove dados antigos das tabelas antes de migrar nova base
    Usa TRUNCATE para ser mais rápido que DELETE
    """
    logger.info("🧼 Limpando dados antigos do banco...")
    
    tabelas_para_limpar = list(CAMADAS_ALVO.values()) + ['territorios_voronoi', 'cache_mercado']
    
    try:
        with engine.connect() as conn:
            for tabela in tabelas_para_limpar:
                try:
                    conn.execute(text(f"TRUNCATE TABLE {tabela} CASCADE"))
                    logger.info(f"  ✅ Tabela '{tabela}' limpa")
                except Exception as e:
                    logger.warning(f"  ⚠️  Tabela '{tabela}': {e}")
            
            conn.commit()
            logger.info("✅ Limpeza concluída!")
    except Exception as e:
        logger.error(f"❌ Erro ao limpar dados: {e}")
        raise

def migrar_gdb_para_sql(limpar_antes=True):
    """
    Migra dados do GDB para PostgreSQL
    
    Args:
        limpar_antes: Se True, limpa dados antigos antes de migrar
    """
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
    
    if limpar_antes:
        try:
            limpar_dados_antigos(engine)
        except Exception as e:
            logger.error(f"❌ Erro ao limpar dados antigos: {e}")
            logger.info("⚠️  Continuando com a migração...")

    for layer_gdb, nome_tabela in CAMADAS_ALVO.items():
        logger.info(f"--------------------------------------------------")
        logger.info(f"🔄 Processando camada: {layer_gdb} -> Tabela: {nome_tabela}")
        
        try:
            # engine='pyogrio' removido pois a lib foi removida do requirements.
            gdf = gpd.read_file(PATH_GDB, layer=layer_gdb)
            
            if gdf.empty:
                logger.warning(f"⚠️ Camada {layer_gdb} vazia.")
                continue

            e_mapa = isinstance(gdf, gpd.GeoDataFrame)

            if e_mapa:
                if gdf.crs and gdf.crs.to_string() != "EPSG:4326":
                    gdf = gdf.to_crs("EPSG:4326")
                
                logger.info(f"   🗺️  Salvando MAPA ({len(gdf)} registros)...")
                gdf.to_postgis(nome_tabela, engine, if_exists='replace', index=False, chunksize=5000)
            
            else:
                logger.info(f"   📄 Salvando TABELA ({len(gdf)} registros)...")
                
                if 'geometry' in gdf.columns:
                    gdf = gdf.drop(columns=['geometry'])
                
                gdf.to_sql(nome_tabela, engine, if_exists='replace', index=False, chunksize=10000)
            
            logger.info(f"✅ Sucesso!")

        except ValueError:
            logger.warning(f"⚠️ Camada {layer_gdb} não encontrada no arquivo.")
        except Exception as e:
            logger.error(f"❌ Erro crítico em {layer_gdb}: {e}")

    logger.info("🏁 MIGRACAO CONCLUÍDA COM SUCESSO 🏁")

if __name__ == "__main__":
    migrar_gdb_para_sql()