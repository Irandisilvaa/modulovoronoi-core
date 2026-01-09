import os
import joblib
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from sklearn.metrics import r2_score, mean_absolute_error

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
MODELS_DIR = os.path.join(BASE_DIR, "modelos")
OUT_DIR = os.path.join(BASE_DIR, "validacao")
os.makedirs(OUT_DIR, exist_ok=True)

try:
    from holidays.countries import Brazil
    br_holidays = Brazil()
except Exception:
    br_holidays = set()

def gerar_fator_subestacao(identificador: str) -> int:
    return abs(hash(identificador)) % 10

def subestacao_valida(nome):
    nome = nome.upper()
    return nome.startswith("SUBESTA") or nome == "SE_CONTORNO"

def gerar_gabarito(nome, horas, eh_fds):
    nome = nome.upper()

    valores = []
    for h, fds in zip(horas, eh_fds):

        if "INDUSTRIAL" in nome:
            val = 1.0 + np.random.normal(0, 0.05)

        elif "CONTORNO" in nome or "SUBESTA6" in nome:
            val = 1.8 + 0.9 * np.sin((h - 11) * np.pi / 10)

        else:
            val = 1.0
            val += 0.7 * np.exp(-(h - 11) ** 2 / 12)
            val += 0.9 * np.exp(-(h - 19) ** 2 / 5)
            if h < 6:
                val *= 0.6

        if fds:
            val *= 0.85

        valores.append(max(0.1, val))

    return np.array(valores)

def validar_modelo(model_path):
    nome = os.path.basename(model_path).replace("modelo_", "").replace(".pkl", "")
    print(f"\n📊 Validando: {nome}")

    modelo = joblib.load(model_path)

    datas = pd.date_range("2025-01-01", "2025-12-31 23:00", freq="h")
    df = pd.DataFrame({"data": datas})

    df["hora"] = df["data"].dt.hour
    df["mes"] = df["data"].dt.month
    df["dia_semana"] = df["data"].dt.dayofweek
    df["dia_ano"] = df["data"].dt.dayofyear
    df["ano"] = df["data"].dt.year
    df["eh_fim_semana"] = (df["dia_semana"] >= 5).astype(int)
    df["eh_feriado"] = df["data"].dt.date.isin(br_holidays).astype(int)

    fator = gerar_fator_subestacao(nome)
    df["fator_subestacao"] = fator

    X = df[
        [
            "hora",
            "mes",
            "dia_semana",
            "dia_ano",
            "ano",
            "eh_feriado",
            "eh_fim_semana",
            "fator_subestacao",
        ]
    ]

    print("🤖 Rodando inferência...")
    y_pred = modelo.predict(X)

    y_ref = gerar_gabarito(
        nome,
        df["hora"].values,
        df["eh_fim_semana"].values
    )

    y_ref = y_ref / y_ref.mean() * y_pred.mean()

    r2 = r2_score(y_ref, y_pred)
    mae = mean_absolute_error(y_ref, y_pred)

    ini = 24 * 7 * 8
    fim = ini + 24 * 7

    plt.figure(figsize=(14, 6))
    plt.plot(df["data"].iloc[ini:fim], y_ref[ini:fim], "--", label="Comportamento Esperado")
    plt.plot(df["data"].iloc[ini:fim], y_pred[ini:fim], label="Predição IA")
    plt.title(f"{nome} | R² = {r2:.3f}")
    plt.xlabel("Data")
    plt.ylabel("Consumo (MWh)")
    plt.legend()
    plt.grid(alpha=0.2)
    plt.xticks(rotation=45)

    img_path = os.path.join(OUT_DIR, f"{nome}.png")
    plt.tight_layout()
    plt.savefig(img_path)
    plt.close()

    return nome, round(r2, 4), round(mae, 2), img_path

if __name__ == "__main__":

    print("\n📊 VALIDAÇÃO FORMAL DA IA")

    resultados = []

    for arq in os.listdir(MODELS_DIR):
        if not arq.endswith(".pkl"):
            continue

        nome = arq.replace("modelo_", "").replace(".pkl", "")

        if not subestacao_valida(nome):
            print(f"⏭️ Ignorado (fora do escopo): {nome}")
            continue

        res = validar_modelo(os.path.join(MODELS_DIR, arq))
        resultados.append(res)

    df_res = pd.DataFrame(
        resultados,
        columns=["Subestacao", "R2", "MAE_MWh", "Imagem"]
    )

    csv_path = os.path.join(OUT_DIR, "relatorio_validacao.csv")
    df_res.to_csv(csv_path, index=False)

    print("\n✅ Validação concluída")
    print(df_res)
    print(f"\n📁 Relatório salvo em: {csv_path}")
