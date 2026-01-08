"""
Camada de Acesso a Dados (DAL) - Database Access Layer
Centraliza todas as operações com o banco de dados PostgreSQL/PostGIS
"""
import os
import sys
import logging
import geopandas as gpd
import pandas as pd
from sqlalchemy import create_engine, text
from typing import Optional, List

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from config import DATABASE_URL

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("Database")


def get_engine():
    """
    Retorna engine SQLAlchemy configurada para PostgreSQL/PostGIS
    
    Returns:
        Engine: SQLAlchemy engine configurado
    """
    try:
        engine = create_engine(DATABASE_URL)
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        logger.info("✅ Conexão com banco de dados estabelecida")
        return engine
    except Exception as e:
        logger.error(f"❌ Erro ao conectar no banco de dados: {e}")
        raise


def carregar_subestacoes(colunas: Optional[List[str]] = None) -> gpd.GeoDataFrame:
    """
    Carrega dados da tabela 'subestacoes' (SUB)
    
    Args:
        colunas: Lista de colunas específicas a carregar. None = todas
        
    Returns:
        GeoDataFrame com dados das subestações
    """
    engine = get_engine()
    
    try:
        if colunas:
            cols_sql = ", ".join([f'"{c}"' if c != 'geometry' else c for c in colunas])
            if "geometry" not in colunas:
                cols_sql += ", geometry"
            sql = f'SELECT {cols_sql} FROM subestacoes'
        else:
            sql = "SELECT * FROM subestacoes"
        
        gdf = gpd.read_postgis(sql, engine, geom_col='geometry')
        logger.info(f"📥 Carregadas {len(gdf)} subestações do banco")
        return gdf
    except Exception as e:
        logger.error(f"❌ Erro ao carregar subestações: {e}")
        raise
    finally:
        engine.dispose()


def carregar_transformadores(colunas: Optional[List[str]] = None) -> gpd.GeoDataFrame:
    """
    Carrega dados da tabela 'transformadores' (UNTRAT_AT)
    
    Args:
        colunas: Lista de colunas específicas a carregar. None = todas
        
    Returns:
        GeoDataFrame com dados dos transformadores
    """
    engine = get_engine()
    
    try:
        if colunas:
            cols_sql = ", ".join([f'"{col}"' for col in colunas])
            if 'geometry' not in colunas:
                sql = f"SELECT {cols_sql}, geometry FROM transformadores"
            else:
                sql = f"SELECT {cols_sql} FROM transformadores"
        else:
            sql = "SELECT * FROM transformadores"
        
        gdf = gpd.read_postgis(sql, engine, geom_col='geometry')
        
        logger.info(f"📥 Carregados {len(gdf)} transformadores do banco")
        return gdf
    except Exception as e:
        logger.error(f"❌ Erro ao carregar transformadores: {e}")
        raise
    finally:
        engine.dispose()


def carregar_consumidores(colunas: Optional[List[str]] = None, ignore_geometry: bool = False) -> pd.DataFrame:
    """
    Carrega dados da tabela 'consumidores' (UCBT_tab)
    NOTA: Esta tabela não possui geometria no PostgreSQL
    
    Args:
        colunas: Lista de colunas específicas a carregar. None = todas
        ignore_geometry: Ignorado, mantido para compatibilidade
        
    Returns:
        DataFrame com dados dos consumidores
    """
    engine = get_engine()
    
    try:
        if colunas:
            cols_sql = ", ".join([f'"{col}"' for col in colunas])
        else:
            cols_sql = "*"
        
        sql = f"SELECT {cols_sql} FROM consumidores"
        
        df = pd.read_sql(sql, engine)
        
        logger.info(f"📥 Carregados {len(df)} consumidores do banco")
        return df
    except Exception as e:
        logger.error(f"❌ Erro ao carregar consumidores: {e}")
        raise
    finally:
        engine.dispose()


def carregar_geracao_gd(colunas: Optional[List[str]] = None, ignore_geometry: bool = False) -> pd.DataFrame:
    """
    Carrega dados da tabela 'geracao_gd' (UGBT_tab)
    NOTA: Esta tabela não possui geometria no PostgreSQL
    
    Args:
        colunas: Lista de colunas específicas a carregar. None = todas
        ignore_geometry: Ignorado, mantido para compatibilidade
        
    Returns:
        DataFrame com dados de geração distribuída
    """
    engine = get_engine()
    
    try:
        if colunas:
            cols_sql = ", ".join([f'"{col}"' for col in colunas])
        else:
            cols_sql = "*"
        
        sql = f"SELECT {cols_sql} FROM geracao_gd"
        
        df = pd.read_sql(sql, engine)
        
        logger.info(f"📥 Carregados {len(df)} registros de GD do banco")
        return df
    except Exception as e:
        logger.error(f"❌ Erro ao carregar geração distribuída: {e}")
        raise
    finally:
        engine.dispose()


def carregar_rede_mt(colunas: Optional[List[str]] = None) -> gpd.GeoDataFrame:
    """
    Carrega dados da tabela 'rede_mt' (SSDMT)
    
    Args:
        colunas: Lista de colunas específicas a carregar. None = todas
        
    Returns:
        GeoDataFrame com dados da rede MT
    """
    engine = get_engine()
    
    try:
        if colunas:
            cols_sql = ", ".join(colunas + ["geometry"]) if "geometry" not in colunas else ", ".join(colunas)
            sql = f"SELECT {cols_sql} FROM rede_mt"
        else:
            sql = "SELECT * FROM rede_mt"
        
        gdf = gpd.read_postgis(sql, engine, geom_col='geometry')
        logger.info(f"📥 Carregados {len(gdf)} trechos de rede MT do banco")
        return gdf
    except Exception as e:
        logger.error(f"❌ Erro ao carregar rede MT: {e}")
        raise
    finally:
        engine.dispose()


def carregar_voronoi() -> gpd.GeoDataFrame:
    """
    Carrega dados da tabela 'territorios_voronoi'
    
    Returns:
        GeoDataFrame com territórios de Voronoi das subestações
    """
    engine = get_engine()
    
    try:
        sql = "SELECT * FROM territorios_voronoi"
        gdf = gpd.read_postgis(sql, engine, geom_col='geometry')
        logger.info(f"📥 Carregados {len(gdf)} territórios Voronoi do banco")
        return gdf
    except Exception as e:
        logger.error(f"❌ Erro ao carregar Voronoi: {e}")
        raise
    finally:
        engine.dispose()


def salvar_voronoi(gdf: gpd.GeoDataFrame) -> None:
    """
    Salva territórios Voronoi no banco de dados
    
    Args:
        gdf: GeoDataFrame com territórios de Voronoi
    """
    engine = get_engine()
    
    try:
        if gdf.crs and gdf.crs.to_string() != "EPSG:4326":
            gdf = gdf.to_crs("EPSG:4326")
        
        gdf.to_postgis(
            'territorios_voronoi', 
            engine, 
            if_exists='replace', 
            index=False
        )
        logger.info(f"💾 Salvos {len(gdf)} territórios Voronoi no banco")
    except Exception as e:
        logger.error(f"❌ Erro ao salvar Voronoi: {e}")
        raise
    finally:
        engine.dispose()


def criar_tabela_cache():
    """
    Cria tabela de cache de mercado se não existir
    Usa JSONB para armazenar dados agregados de forma eficiente
    """
    engine = get_engine()
    
    try:
        with engine.connect() as conn:
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS cache_mercado (
                    id_subestacao VARCHAR PRIMARY KEY,
                    dados_json JSONB NOT NULL,
                    data_atualizacao TIMESTAMP DEFAULT NOW()
                )
            """))
            conn.commit()
            logger.info("✅ Tabela cache_mercado verificada/criada")
    except Exception as e:
        logger.error(f"❌ Erro ao criar tabela cache: {e}")
        raise
    finally:
        engine.dispose()


def salvar_cache_mercado(dados_mercado: list) -> None:
    """
    Salva dados agregados de mercado no banco de dados
    
    Args:
        dados_mercado: Lista de dicts com dados agregados por subestação
    """
    import json
    
    engine = get_engine()
    
    try:
        criar_tabela_cache()
        
        with engine.connect() as conn:
            conn.execute(text("DELETE FROM cache_mercado"))
            
            for item in dados_mercado:
                id_sub = item.get('id_tecnico', str(item.get('subestacao', '')))
                
                item_clean = {k: v for k, v in item.items() if k != 'geometry'}
                
                conn.execute(
                    text("""
                        INSERT INTO cache_mercado (id_subestacao, dados_json, data_atualizacao)
                        VALUES (:id, CAST(:dados AS jsonb), NOW())
                        ON CONFLICT (id_subestacao) 
                        DO UPDATE SET dados_json = CAST(:dados AS jsonb), data_atualizacao = NOW()
                    """),
                    {"id": id_sub, "dados": json.dumps(item_clean, ensure_ascii=False)}
                )
            
            conn.commit()
            logger.info(f"💾 Salvos {len(dados_mercado)} registros de cache no banco")
            
    except Exception as e:
        logger.error(f"❌ Erro ao salvar cache: {e}")
        raise
    finally:
        engine.dispose()


def carregar_cache_mercado() -> list:
    """
    Carrega dados agregados de mercado do banco de dados
    
    Returns:
        Lista de dicts com dados agregados por subestação
    """
    import json
    
    engine = get_engine()
    
    try:
        with engine.connect() as conn:
            result = conn.execute(text("""
                SELECT dados_json 
                FROM cache_mercado 
                ORDER BY id_subestacao
            """))
            
            dados = []
            for row in result:
                item = row[0]
                if isinstance(item, str):
                    dados.append(json.loads(item))
                else:
                    dados.append(item)
            
            logger.info(f"📥 Carregados {len(dados)} registros de cache do banco")
            return dados
            
    except Exception as e:
        logger.error(f"❌ Erro ao carregar cache: {e}")
        raise
    finally:
        engine.dispose()


def verificar_cache_atualizado(max_horas: int = 24) -> bool:
    """
    Verifica se o cache está atualizado (menos de X horas)
    
    Args:
        max_horas: Número máximo de horas para considerar cache válido
        
    Returns:
        True se cache está atualizado, False caso contrário
    """
    engine = get_engine()
    
    try:
        with engine.connect() as conn:
            result = conn.execute(text("""
                SELECT MAX(data_atualizacao) as ultima_atualizacao
                FROM cache_mercado
            """))
            
            row = result.fetchone()
            
            if not row or not row[0]:
                logger.info("⚠️ Cache vazio ou inexistente")
                return False
            
            ultima_atualizacao = row[0]
            
            from datetime import datetime, timedelta
            agora = datetime.now()
            diferenca = agora - ultima_atualizacao
            
            if diferenca.total_seconds() / 3600 < max_horas:
                logger.info(f"✅ Cache atualizado (última atualização: {ultima_atualizacao})")
                return True
            else:
                logger.info(f"⚠️ Cache desatualizado (última atualização: {ultima_atualizacao})")
                return False
                
    except Exception as e:
        logger.warning(f"⚠️ Erro ao verificar cache: {e}")
        return False
    finally:
        engine.dispose()





def verificar_tabelas() -> dict:
    """
    Verifica quais tabelas existem no banco e retorna contagem de registros
    
    Returns:
        Dict com nome da tabela e contagem de registros
    """
    engine = get_engine()
    
    tabelas = [
        'subestacoes',
        'transformadores',
        'consumidores',
        'geracao_gd',
        'rede_mt',
        'territorios_voronoi',
        'cache_mercado'
    ]
    
    resultado = {}
    
    try:
        with engine.connect() as conn:
            for tabela in tabelas:
                try:
                    result = conn.execute(text(f"SELECT COUNT(*) FROM {tabela}"))
                    count = result.scalar()
                    resultado[tabela] = count
                    logger.info(f"✅ {tabela}: {count} registros")
                except Exception as e:
                    resultado[tabela] = f"Erro: {str(e)}"
                    logger.warning(f"⚠️ {tabela}: não encontrada ou erro")
        
        return resultado
    except Exception as e:
        logger.error(f"❌ Erro ao verificar tabelas: {e}")
        raise
    finally:
        engine.dispose()


if __name__ == "__main__":
    """Testa conexão e lista tabelas disponíveis"""
    print("🔌 Testando conexão com banco de dados...")
    print("=" * 60)
    
    try:
        engine = get_engine()
        print(f"✅ Conectado em: {DATABASE_URL.split('@')[1]}")
        print("=" * 60)
        print("\n📊 Verificando tabelas e contagens:")
        print("=" * 60)
        
        resultado = verificar_tabelas()
        
        print("\n" + "=" * 60)
        print("✅ Teste concluído com sucesso!")
        
    except Exception as e:
        print(f"\n❌ Falha no teste: {e}")
        sys.exit(1)
