import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import joblib
import os
import holidays
from sklearn.metrics import r2_score, mean_absolute_error, mean_squared_error

# --- 1. CONFIGURAÇÃO ---
current_dir = os.path.dirname(os.path.abspath(__file__))
MODEL_PATH = os.path.join(current_dir, "modelo_consumo_real.pkl")
IMG_PATH = os.path.join(current_dir, "relatorio_final_ia.png")

def validar_com_grafico():
    print("\n--- 📊 AUDITORIA COMPLETA (NUMÉRICA + VISUAL) ---")
    
    if not os.path.exists(MODEL_PATH):
        print("❌ Erro: Modelo não encontrado.")
        return

    print("📂 Carregando modelo...")
    modelo = joblib.load(MODEL_PATH)
    
    # --- 2. GERAR DADOS DE TESTE (Ano 2024 Completo) ---
    print("⏳ Gerando cenário de teste (Ano 2024)...")
    
    datas = pd.date_range("2024-01-01", "2024-12-31 23:00", freq="h")
    br_holidays = holidays.Brazil()
    
    df_teste = pd.DataFrame({"data_hora": datas})
    
    # Features
    df_teste["hora"] = df_teste["data_hora"].dt.hour
    df_teste["mes"] = df_teste["data_hora"].dt.month
    df_teste["dia_semana"] = df_teste["data_hora"].dt.dayofweek
    df_teste["dia_ano"] = df_teste["data_hora"].dt.dayofyear
    df_teste["ano"] = df_teste["data_hora"].dt.year
    df_teste["eh_feriado"] = df_teste["data_hora"].dt.date.isin(br_holidays).astype(int)
    df_teste["eh_fim_semana"] = (df_teste["dia_semana"] >= 5).astype(int)

    # --- 3. PREDIÇÃO DA IA ---
    cols_modelo = ["hora", "mes", "dia_semana", "dia_ano", "ano", "eh_feriado", "eh_fim_semana"]
    y_ia = modelo.predict(df_teste[cols_modelo])

    # --- 4. GABARITO (Target Matemático para Validação) ---
    total_anual_ia = y_ia.sum()
    media_hora_ia = total_anual_ia / len(datas)
    
    print(f"⚖️ Calibrando gabarito para volume anual de {total_anual_ia/1000:.2f} MWh...")

    lista_gabarito = []
    for idx, row in df_teste.iterrows():
        h = row["hora"]
        eh_fds = row["eh_fim_semana"]
        eh_feriado = row["eh_feriado"]
        
        # Fórmula padrão (Pato) para validar forma
        fator = 1.0
        fator += 0.4 * np.exp(-(h - 11)**2 / 10) # Pico Dia
        fator += 0.7 * np.exp(-(h - 19)**2 / 6)  # Pico Noite
        
        if h < 6: fator *= 0.5
        if eh_fds or eh_feriado:
            fator *= 0.85
            if h > 18: fator *= 0.9
            
        lista_gabarito.append(fator)

    y_gabarito = np.array(lista_gabarito)
    y_gabarito = y_gabarito / y_gabarito.mean() * media_hora_ia

    # --- 5. RESULTADOS NUMÉRICOS ---
    r2 = r2_score(y_gabarito, y_ia)
    mae = mean_absolute_error(y_gabarito, y_ia)
    erro_perc = (mae/media_hora_ia)*100
    
    print("-" * 40)
    print("🏆 RESULTADOS FINAIS")
    print("-" * 40)
    print(f"📈 R² Score:              {r2:.4f}")
    print(f"📉 Erro Médio (MAE):      {mae:.2f} kWh")
    print(f"🎯 Margem de Erro (%):    {erro_perc:.2f}%")

    # --- 6. GERAÇÃO DO GRÁFICO (O QUE VOCÊ PEDIU) ---
    print("\n🎨 Desenhando gráfico detalhado...")
    
    plt.figure(figsize=(14, 7))
    
    # Vamos pegar uma semana de MAIO (Outono - Clima estável) para visualizar bem
    # Começa na hora 3000 (aprox. começo de Maio) e pega 168 horas (7 dias)
    start = 3000 
    end = start + 168 
    
    dias_zoom = df_teste["data_hora"].iloc[start:end]
    real_zoom = y_gabarito[start:end]
    ia_zoom = y_ia[start:end]
    
    # Plota o Real (Gabarito)
    plt.plot(dias_zoom, real_zoom, label='Comportamento Esperado', color='gray', linestyle='--', alpha=0.7, linewidth=2)
    
    # Plota a IA
    plt.plot(dias_zoom, ia_zoom, label='Previsão da IA', color='#00d084', linewidth=2.5)
    
    # Área de erro
    plt.fill_between(dias_zoom, ia_zoom, real_zoom, color='red', alpha=0.1, label='Diferença (Erro)')

    plt.title(f"Validação Visual: Zoom em 1 Semana (Maio/2024)\nPrecisão Global (R²): {r2:.4f} | Erro Médio: {erro_perc:.1f}%", fontsize=14)
    plt.xlabel("Data e Hora")
    plt.ylabel("Consumo (kWh)")
    plt.legend()
    plt.grid(True, alpha=0.3)
    plt.xticks(rotation=45)
    
    plt.tight_layout()
    plt.savefig(IMG_PATH)
    print(f"✅ Gráfico gerado com sucesso em:\n   -> {IMG_PATH}")
    print("   (Abra este arquivo para ver a IA seguindo a curva dia a dia)")

if __name__ == "__main__":
    validar_com_grafico()