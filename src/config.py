import os
from dotenv import load_dotenv

DIR_SRC = os.path.dirname(os.path.abspath(__file__))
DIR_RAIZ = os.path.dirname(DIR_SRC)

DIR_DADOS = os.path.join(DIR_RAIZ, "dados")

path_env = os.path.join(DIR_RAIZ, '.env')
load_dotenv(path_env)

# Configuração de Banco de Dados
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://postgres:1234@localhost:5433/gridscope_local")

# Configurações de Negócio
CIDADE_ALVO = os.getenv("CIDADE_ALVO", "Aracaju, Sergipe, Brazil")
CRS_PROJETADO = "EPSG:31984"

ANEEL_API_HUB_URL = os.getenv("ANEEL_API_HUB_URL", "https://hub.arcgis.com/api/search/v1/collections/all/items")
DISTRIBUIDORA_ALVO = os.getenv("DISTRIBUIDORA_ALVO", "Energisa SE")