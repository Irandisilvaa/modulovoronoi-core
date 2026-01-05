import os
import joblib
import pandas as pd
import numpy as np
from fastapi import FastAPI
from pydantic import BaseModel, field_validator
from datetime import date, datetime

try:
    from holidays.countries import Brazil
    br_holidays = Brazil()
except Exception:
    br_holidays = set()

current_dir = os.path.dirname(os.path.abspath(__file__))
MODELS_DIR = os.path.join(current_dir, "modelos")


class ModelCache:
    _instance = None
    _modelos = {}

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._modelos = {}
        return cls._instance

    def obter_modelo(self, sub_id):
        if not sub_id:
            return None

        sub_id = sub_id.strip().replace(" ", "_")

        if sub_id in self._modelos:
            return self._modelos[sub_id]

        path = os.path.join(MODELS_DIR, f"modelo_{sub_id}.pkl")
        if os.path.exists(path):
            self._modelos[sub_id] = joblib.load(path)
            print(f"✅ Modelo carregado: {sub_id}")
            return self._modelos[sub_id]

        return None


_cache = ModelCache()
app = FastAPI(title="GridScope AI", version="9.0")


class DuckCurveInput(BaseModel):
    subestacao_id: str
    data_alvo: date
    capacidade_gd_mw: float
    fator_sol: float

    @field_validator("data_alvo", mode="before")
    @classmethod
    def parse_date(cls, v):
        if isinstance(v, datetime):
            return v.date()
        if isinstance(v, str):
            return date.fromisoformat(v[:10])
        return v

def gerar_fator_subestacao(sub_id: str) -> int:
    return abs(hash(sub_id)) % 10


def gerar_features(data_str, sub_id):
    data = pd.to_datetime(data_str)

    eh_fds = data.dayofweek >= 5
    eh_feriado = data.date() in br_holidays
    fator_sub = gerar_fator_subestacao(sub_id)

    rows = []
    for h in range(24):
        rows.append({
            "hora": h,
            "mes": data.month,
            "dia_semana": data.dayofweek,
            "dia_ano": data.dayofyear,
            "ano": data.year,
            "eh_feriado": int(eh_feriado),
            "eh_fim_semana": int(eh_fds),
            "fator_subestacao": fator_sub
        })

    return pd.DataFrame(rows)


@app.post("/predict/duck-curve")
def predict(entrada: DuckCurveInput):
    try:
        modelo = _cache.obter_modelo(entrada.subestacao_id)
        df = gerar_features(entrada.data_alvo, entrada.subestacao_id)
    except Exception as e:
        print("❌ ERRO AO PREPARAR DADOS:", e)
        return {
            "erro": "Falha ao preparar dados de entrada",
            "detalhe": str(e)
        }

    if modelo:
        try:
            consumo = modelo.predict(df)
            consumo = np.maximum(consumo, 0)

            ruido = np.random.normal(0, 0.12, 24)
            consumo = (consumo * (1 + ruido)).tolist()
            fonte = "IA"

        except Exception as e:
            print("❌ ERRO NA PREDIÇÃO:", e)
            consumo = [1.2] * 24
            fonte = "Fallback (erro predição)"

    else:
        consumo = [1.2] * 24
        fonte = "Fallback (sem modelo)"

    try:
        horas = np.arange(24)
        solar = np.exp(-((horas - 12) ** 2) / (2 * 3.2 ** 2))
        solar = (solar * entrada.capacidade_gd_mw * entrada.fator_sol).tolist()
    except Exception as e:
        print("❌ ERRO NA CURVA SOLAR:", e)
        solar = [0.0] * 24

    carga_liquida = [c - g for c, g in zip(consumo, solar)]

    return {
        "timeline": list(range(24)),
        "consumo_mwh": consumo,
        "geracao_mwh": solar,
        "carga_liquida_mwh": carga_liquida,
        "fonte": fonte
    }
