import logging
import sys
import os
from sqlalchemy import text

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from src.database import get_engine

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def criar_indices():
    """
    Cria índices nas tabelas do PostgreSQL para otimizar consultas.
    """
    engine = get_engine()
    
    indices = [
        "CREATE INDEX IF NOT EXISTS idx_subestacoes_cod_id ON subestacoes (\"COD_ID\");",
        "CREATE INDEX IF NOT EXISTS idx_subestacoes_nome ON subestacoes (\"NOME\");",
        
        "CREATE INDEX IF NOT EXISTS idx_transformadores_cod_id ON transformadores (\"COD_ID\");",
        "CREATE INDEX IF NOT EXISTS idx_transformadores_sub ON transformadores (\"SUB\");",
        "CREATE INDEX IF NOT EXISTS idx_transformadores_geom ON transformadores USING GIST (geometry);",

        "CREATE INDEX IF NOT EXISTS idx_consumidores_uni_tr_mt ON consumidores (\"UNI_TR_MT\");",
        "CREATE INDEX IF NOT EXISTS idx_consumidores_clas_sub ON consumidores (\"CLAS_SUB\");",

        "CREATE INDEX IF NOT EXISTS idx_cache_mercado_id_sub ON cache_mercado (id_subestacao);"
    ]

    try:
        with engine.connect() as conn:
            for sql in indices:
                logger.info(f"🔄 Criando índice: {sql[:50]}...")
                conn.execute(text(sql))
            conn.commit()
            logger.info("✅ Todos os índices foram criados com sucesso!")
            
    except Exception as e:
        logger.error(f"❌ Erro ao criar índices: {e}")
    finally:
        engine.dispose()

if __name__ == "__main__":
    criar_indices()
