import os
from dotenv import load_dotenv

DIR_SRC = os.path.dirname(os.path.abspath(__file__))
DIR_RAIZ = os.path.dirname(DIR_SRC)

path_env = os.path.join(DIR_RAIZ, '.env')
load_dotenv(path_env)

NOME_GDB = os.getenv("FILE_GDB", "Energisa_SE_6587_2023-12-31_V11_20250701-0833.gdb")
NOME_GEOJSON = os.getenv("FILE_GEOJSON", "subestacoes_logicas_aracaju.geojson")
NOME_JSON_MERCADO = os.getenv("FILE_MERCADO", "perfil_mercado_aracaju.json")

PATH_GDB = os.path.join(DIR_RAIZ, "dados", NOME_GDB)
PATH_GEOJSON = os.path.join(DIR_RAIZ, NOME_GEOJSON)
PATH_JSON_MERCADO = os.path.join(DIR_RAIZ, NOME_JSON_MERCADO)

CIDADE_ALVO = os.getenv("CIDADE_ALVO", "Aracaju, Sergipe, Brazil")
CRS_PROJETADO = "EPSG:31984"