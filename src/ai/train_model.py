import os
import joblib
import pandas as pd
import numpy as np
from sklearn.ensemble import RandomForestRegressor
import holidays


current_dir = os.path.dirname(os.path.abspath(__file__))

MODEL_PATH = os.path.join(current_dir, "modelo_consumo.pkl") 


CURVA_RES = np.array([
    0.4, 0.35, 0.3, 0.3, 0.3, 0.35, 0.5, 0.6, 0.55, 0.5, 
    0.45, 0.45, 0.45, 0.5, 0.55, 0.6, 0.7, 0.9, 1.2, 1.1, 
    1.0, 0.9, 0.7, 0.5
]) 

CURVA_COM = np.array([
    0.2, 0.2, 0.2, 0.2, 0.2, 0.3, 0.5, 0.8, 1.0, 1.1, 
    1.1, 1.1, 1.0, 1.1, 1.1, 1.1, 1.0, 0.9, 0.6, 0.4, 
    0.3, 0.25, 0.2, 0.2
]) 

CURVA_IND = np.array([
    0.7, 0.7, 0.7, 0.7, 0.75, 0.8, 0.9, 0.95, 1.0, 1.0, 
    1.0, 1.0, 0.95, 1.0, 1.0, 1.0, 0.95, 0.9, 0.8, 0.8, 
    0.75, 0.75, 0.7, 0.7
]) 

CURVA_RUR = np.array([
    0.3, 0.3, 0.3, 0.4, 0.5, 0.6, 0.7, 0.7, 0.6, 0.6,
    0.6, 0.6, 0.6, 0.6, 0.6, 0.7, 0.8, 1.0, 0.9, 0.7,
    0.5, 0.4, 0.3, 0.3
])

def gerar_dados_treino_inteligente():
    """
    Gera um dataset massivo misturando aleatoriamente os perfis (DNA)
    para ensinar o modelo a reagir a qualquer tipo de subestação.
    """
    print("🔄 Gerando dataset de treinamento sintético inteligente...")
    
    br_holidays = holidays.Brazil()
    datas = pd.date_range(start="2023-01-01", end="2023-12-31", freq="h")
    
    features = []

    perfis_mock = [
        "SUB_RESIDENCIAL", "SUB_INDUSTRIAL", "SUB_COMERCIAL", "SUB_MISTA", "SUB_RURAL"
    ]

    for i in range(50):
        tipo_sub = np.random.choice(perfis_mock)
        identificador_str = f"{tipo_sub}_{i}"    
        nome_upper = identificador_str.upper()

        if "SUB_RESIDENCIAL" in nome_upper:
            p_res, p_com, p_ind, p_rur = 0.8, 0.1, 0.1, 0.0
        elif "SUB_INDUSTRIAL" in nome_upper:
            p_res, p_com, p_ind, p_rur = 0.1, 0.1, 0.8, 0.0
        elif "SUB_COMERCIAL" in nome_upper:
            p_res, p_com, p_ind, p_rur = 0.1, 0.8, 0.1, 0.0
        elif "SUB_RURAL" in nome_upper:
            p_res, p_com, p_ind, p_rur = 0.2, 0.1, 0.0, 0.7
        else:
            p_res, p_com, p_ind, p_rur = 0.4, 0.3, 0.3, 0.0

        curva_mista_base = (CURVA_RES * p_res) + \
                           (CURVA_COM * p_com) + \
                           (CURVA_IND * p_ind) + \
                           (CURVA_RUR * p_rur)

        for data in datas:
            h = data.hour
            mes = data.month
            
            consumo_base = curva_mista_base[h] * 100 
            
            eh_fds = data.dayofweek >= 5
            eh_feriado = data.date() in br_holidays
            
            fator_fds = 0.85 if eh_fds or eh_feriado else 1.0
            
            fator_sazonal = 1.0
            if mes in [12, 1, 2, 3]: # Verão
                fator_sazonal = 1.15
            elif mes in [6, 7]: 
                fator_sazonal = 0.9
                
            # Ruído aleatório (realidade)
            ruido = np.random.normal(0, 0.05)
            
            # Cálculo final do target
            consumo_final = consumo_base * fator_fds * fator_sazonal + ruido
            consumo_final = max(0.01, consumo_final)

            features.append({
                "hora": h,
                "mes": mes,
                "dia_semana": data.dayofweek,
                "eh_feriado": int(eh_feriado),
                "eh_fim_semana": int(eh_fds),
                # O PULO DO GATO: Passamos o DNA como feature!
                "pct_residencial": p_res,
                "pct_comercial": p_com,
                "pct_industrial": p_ind,
                "pct_rural": p_rur,
                # Target
                "fator_consumo": consumo_final
            })

    return pd.DataFrame(features)

def treinar_modelo_universal():
    """
    Treina um único modelo Random Forest robusto capaz de prever 
    qualquer perfil de subestação baseado no DNA informado.
    """
    df = gerar_dados_treino_inteligente()
    
    print(f"📊 Dataset gerado com {len(df)} amostras.")
    print("🚀 Iniciando treinamento do Modelo Universal...")
    
    X = df.drop(columns=["fator_consumo"])
    y = df["fator_consumo"]
    
    model = RandomForestRegressor(
        n_estimators=100,
        max_depth=15, 
        random_state=42,
        n_jobs=-1
    )
    
    model.fit(X, y)
    
    print(f"💾 Salvando modelo em: {MODEL_PATH}")
    joblib.dump(model, MODEL_PATH)
    print("✅ Modelo Universal Treinado com Sucesso!")

if __name__ == "__main__":
    treinar_modelo_universal()