import os
import joblib
import pandas as pd
import numpy as np
from sklearn.ensemble import RandomForestRegressor
from datetime import datetime
import holidays

current_dir = os.path.dirname(os.path.abspath(__file__))
MODELS_DIR = os.path.join(current_dir, "modelos")
os.makedirs(MODELS_DIR, exist_ok=True)

def gerar_fator_subestacao(identificador: str) -> int:
    return abs(hash(identificador)) % 10


def treinar_modelo_simulado(identificador):
    identificador_str = str(identificador).strip()
    nome_arquivo = identificador_str.replace(" ", "_")

    print(f"🔄 Treinando modelo para: {identificador_str}")

    try:
        seed = int(''.join(filter(str.isdigit, identificador_str))) * 97
    except:
        seed = sum(ord(c) for c in identificador_str)

    np.random.seed(seed)

    fator_sub = gerar_fator_subestacao(identificador_str)

    datas = pd.date_range(end=datetime.now(), periods=365 * 24, freq="h")
    features = []

    nome_upper = identificador_str.upper()
    br_holidays = holidays.Brazil()

    for data in datas:
        h = data.hour

        if "30290967" in identificador_str:
            consumo_base = 25 + 8 * np.sin((h - 8) * np.pi / 12)
        elif "30290937" in identificador_str:  # SUBESTA7 (B)
            consumo_base = 20 + 12 * np.sin((h - 18) * np.pi / 12)
        elif "CONTORNO" in nome_upper or "SUBESTA6" in nome_upper:
            consumo_base = 35 + 10 * np.sin((h - 10) * np.pi / 10)
        elif "INDUSTRIAL" in nome_upper:
            consumo_base = 45 + np.random.uniform(-3, 3)
        else:
            consumo_base = 18 + 12 * np.sin((h - 6) * np.pi / 12)
            if 18 <= h <= 22:
                consumo_base += 12

        ruido = np.random.normal(0, 2.5)
        consumo = max(0, consumo_base + ruido)

        eh_fds = data.dayofweek >= 5
        eh_feriado = data.date() in br_holidays

        if eh_fds or eh_feriado:
            consumo *= 0.8

        features.append({
            "hora": h,
            "mes": data.month,
            "dia_semana": data.dayofweek,
            "dia_ano": data.dayofyear,
            "ano": data.year,
            "eh_feriado": int(eh_feriado),
            "eh_fim_semana": int(eh_fds),
            "fator_subestacao": fator_sub,
            "consumo": consumo
        })

    df = pd.DataFrame(features)

    X = df.drop(columns=["consumo"])
    y = df["consumo"]

    model = RandomForestRegressor(
        n_estimators=80,
        random_state=seed,
        n_jobs=-1
    )

    model.fit(X, y)

    path = os.path.join(MODELS_DIR, f"modelo_{nome_arquivo}.pkl")
    joblib.dump(model, path)

    print(f"✅ Modelo salvo: {path}")


if __name__ == "__main__":
    lista_treino = [
        "30290967",
        "30290937",
        "30290936",
        "30290965",
        "30290955",
        "30290938",
        "30290969",

        "SUBESTA5",
        "SUBESTA6",
        "SUBESTA7",
        "SUBESTA8",
        "SUBESTA9",
        "SE CONTORNO",
        "Industrial",
        "Centro",
        "Zona Norte"
    ]

    print(f"🚀 Iniciando treinamento de {len(lista_treino)} modelos...")

    for item in lista_treino:
        treinar_modelo_simulado(item)

    print("\n✨ Treinamento finalizado! Reinicie o ai_service.py.")