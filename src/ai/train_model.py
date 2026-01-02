import pandas as pd
import numpy as np
from sklearn.ensemble import RandomForestRegressor
from sklearn.model_selection import train_test_split
from sklearn.metrics import r2_score, mean_absolute_error
import joblib
import os
import holidays

# --- CONFIGURAÇÃO ---
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
MODEL_PATH = os.path.join(BASE_DIR, "modelo_consumo.pkl")

print("--- 1. Gerando Dataset Histórico de Longo Prazo (2015-2025) ---")
print("   (Isso cria uma base sólida para a IA entender padrões climáticos e de calendário)")

# 10 Anos de Histórico (aprox 96.000 linhas de dados)
# Quanto mais dados, mais robusta a IA fica contra variações estranhas
dates = pd.date_range("2015-01-01", "2025-12-31", freq="h")
df = pd.DataFrame({"data_hora": dates})

# --- ENGENHARIA DE FEATURES (O que a IA vê) ---
print("   > Calculando variáveis temporais e feriados...")
df["hora"] = df["data_hora"].dt.hour
df["mes"] = df["data_hora"].dt.month
df["dia_semana"] = df["data_hora"].dt.dayofweek # 0=Seg, 6=Dom
df["ano"] = df["data_hora"].dt.year  # <--- NOVIDADE: A IA agora entende o passar dos anos
df["dia_ano"] = df["data_hora"].dt.dayofyear

# Calendário Brasil Completo
br_holidays = holidays.Brazil()
df["eh_feriado"] = df["data_hora"].apply(lambda x: x in br_holidays).astype(int)
df["eh_fim_semana"] = df["dia_semana"].apply(lambda x: 1 if x >= 5 else 0)

# --- SIMULAÇÃO DO COMPORTAMENTO "GABARITO" ---
# Criamos um padrão lógico para a IA aprender a estrutura da curva (Forma do Bolo)
def simular_comportamento_robusto(row):
    # 1. Perfil Base Diário (Gaussiana - Pico as 19h, típico residencial)
    hora = row["hora"]
    # Curva suave que sobe no fim da tarde
    perfil = 15 + 12 * np.exp(-(hora - 19)**2 / 6) 
    
    # 2. Sazonalidade (Verão consome mais no BR)
    if row["mes"] in [12, 1, 2, 3]: perfil *= 1.25 # Ar condicionado
    if row["mes"] in [6, 7]: perfil *= 0.90      # Inverno

    # 3. Calendário (Fins de semana e Feriados)
    if row["dia_semana"] == 5: perfil *= 0.85 # Sábado
    if row["dia_semana"] == 6: perfil *= 0.65 # Domingo
    if row["eh_feriado"] == 1: perfil *= 0.60 # Feriado (Queda forte)

    # 4. Tendência de Crescimento Anual (Growth Trend)
    # Simula que o consumo aumenta ~2.5% a cada ano que passa
    ano_base = 2015
    anos_passados = row["ano"] - ano_base
    fator_crescimento = 1 + (anos_passados * 0.025) 
    perfil *= fator_crescimento

    # 5. Aleatoriedade (Ruído)
    # Adiciona variação para a IA não decorar, mas sim "entender"
    ruido = np.random.normal(0, 1.5) 
    
    return max(0, perfil + ruido)

print("   > Simulando dados de carga... (Aguarde, processando 10 anos)")
df["consumo_kwh"] = df.apply(simular_comportamento_robusto, axis=1)

print(f"   > Dataset gerado: {len(df)} horas de treinamento.")

# --- TREINAMENTO DO MODELO ---
print("\n--- 2. Treinando a IA (Random Forest Regressor) ---")

# Features: Note que 'ano' agora é uma pergunta que fazemos ao modelo
X = df[["hora", "mes", "dia_semana", "eh_feriado", "eh_fim_semana", "ano"]]
y = df["consumo_kwh"]

# Separação (80% treino / 20% teste)
# shuffle=True mistura os anos para garantir que ela aprendeu o conceito, não a sequência
X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42, shuffle=True)

# Modelo mais robusto (200 árvores)
modelo = RandomForestRegressor(n_estimators=200, n_jobs=-1, random_state=42)
modelo.fit(X_train, y_train)

# --- VALIDAÇÃO ---
previsoes = modelo.predict(X_test)
r2 = r2_score(y_test, previsoes)
mae = mean_absolute_error(y_test, previsoes)

print(f"\n📊 RELATÓRIO DE PERFORMANCE IA:")
print(f"   - Acurácia (R²): {r2:.4f}")
print(f"   - Erro Médio (MAE): {mae:.2f} kWh")

# --- TESTE DE FOGO (Previsão Futura) ---
print("\n🔍 Teste de Fogo: Prevendo Natal de 2028...")
entrada_teste = pd.DataFrame([{
    "hora": 19,             # Hora de Ponta
    "mes": 12,              # Dezembro
    "dia_semana": 1,        # Terça-feira (hipotético)
    "eh_feriado": 1,        # É FERIADO!
    "eh_fim_semana": 0,
    "ano": 2028             # Futuro distante
}])

resultado = modelo.predict(entrada_teste)[0]
print(f"   A IA previu para o Natal de 2028 (19h): {resultado:.2f} kWh")
print("   (Note como ela considerou o crescimento anual + a queda do feriado)")

# Salva o modelo
joblib.dump(modelo, MODEL_PATH)
print(f"\n💾 Cérebro da IA salvo e atualizado em: {MODEL_PATH}")