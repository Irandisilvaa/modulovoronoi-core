
import redis
import json
import logging
from functools import wraps
from typing import Optional, Any
import os
import sys

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
try:
    from config import REDIS_HOST, REDIS_PORT, REDIS_DB
except ImportError:
    REDIS_HOST = "redis"
    REDIS_PORT = 6379
    REDIS_DB = 0

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

try:
    redis_client = redis.Redis(
        host=REDIS_HOST, 
        port=REDIS_PORT, 
        db=REDIS_DB, 
        decode_responses=True,
        socket_connect_timeout=2
    )
except Exception as e:
    logger.warning(f"⚠️ Redis não configurado corretamente: {e}")
    redis_client = None

def is_redis_available():
    if not redis_client: return False
    try:
        return redis_client.ping()
    except redis.ConnectionError:
        return False

def cache_json(ttl_seconds: int = 300, key_prefix: str = "api_cache"):
    """
    Decorator para cachear respostas JSON de endpoints.
    Chave do cache: prefixo + nome_funcao + argumentos
    """
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            if not is_redis_available():
                return func(*args, **kwargs)

            key_parts = [key_prefix, func.__name__]
            if args: key_parts.extend([str(a) for a in args])
            if kwargs: key_parts.extend([f"{k}={v}" for k, v in kwargs.items()])
            
            cache_key = ":".join(key_parts)
            
            try:
                cached = redis_client.get(cache_key)
                if cached:
                    logger.info(f"⚡ Cache HIT: {cache_key}")
                    return json.loads(cached)
            except Exception as e:
                logger.warning(f"Erro ao ler Redis: {e}")

            result = func(*args, **kwargs)

            try:
                if hasattr(result, 'to_json'):
                    to_save = result.to_json()
                elif hasattr(result, 'dict'):
                    to_save = json.dumps(result.dict())
                else:
                    to_save = json.dumps(result)
                
                redis_client.setex(cache_key, ttl_seconds, to_save)
                logger.info(f"💾 Cache SET: {cache_key} (TTL: {ttl_seconds}s)")
            except Exception as e:
                logger.warning(f"Erro ao salvar Redis: {e}")
            
            return result
        return wrapper
    return decorator

def limpar_cache(padrao: str = "api_cache:*"):
    if not is_redis_available(): return 0
    keys = redis_client.keys(padrao)
    if keys:
        return redis_client.delete(*keys)
    return 0
