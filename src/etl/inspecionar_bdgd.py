import geopandas as gpd
import pandas as pd
import os
import sys

# --- CONFIGURAÇÃO DE CAMINHO AUTOMÁTICA ---
# Em vez de importar do config, vamos achar o arquivo GDB na marra.
# Isso evita o erro de "ModuleNotFoundError".

# Tenta achar o caminho voltando diretórios até achar a pasta "dados"
caminho_atual = os.path.dirname(os.path.abspath(__file__))
PATH_GDB = None

# Procura o arquivo voltando até 3 níveis de pasta
for i in range(4):
    caminho_teste = os.path.join(caminho_atual, "dados", "Energisa_SE_6587_2023-12-31_V11_20250701-0833.gdb")
    if os.path.exists(caminho_teste):
        PATH_GDB = caminho_teste
        break
    # Sobe um nível
    caminho_atual = os.path.dirname(caminho_atual)

# Se ainda não achou, usa um padrão ou pede ajuda
if not PATH_GDB:
    # TENTATIVA FINAL: Caminho hardcoded (Se não funcionar, edite esta linha!)
    PATH_GDB = r"C:\Users\irand\Documents\gridscope-core\dados\Energisa_SE_6587_2023-12-31_V11_20250701-0833.gdb"

def inspecionar():
    print("--- 🕵️‍♂️ INSPEÇÃO DE DADOS ---")
    print(f"Alvo GDB: {PATH_GDB}")

    if not os.path.exists(PATH_GDB):
        print("❌ ERRO CRÍTICO: Arquivo GDB não encontrado!")
        print("Verifique se a pasta 'dados' está na raiz do projeto.")
        return

    # 1. Listar Camadas
    try:
        print("\n📂 Lendo camadas do GDB...")
        layers = gpd.list_layers(PATH_GDB)
        print(layers['name'].tolist())
    except Exception as e:
        print(f"Erro ao ler GDB: {e}")
        return

    # 2. Identificar Tabela de Consumidores
    # Procura por UCBT, CONSUMIDOR ou similar
    nomes_candidatos = ['UCBT', 'UCBT_tab', 'CONSUMIDOR', 'CLIENTE']
    layer_alvo = next((l for l in layers['name'] if any(x in l for x in nomes_candidatos)), None)
    
    if not layer_alvo:
        print("\n⚠️ Não achei camada óbvia de consumidores (UCBT).")
        print("Vou inspecionar a primeira camada 'SUB' ou similar para teste.")
        layer_alvo = layers['name'][0]
    
    print(f"\n🔎 Inspecionando tabela: {layer_alvo}")
    
    # 3. Ler Amostra (Rápido)
    try:
        df = gpd.read_file(PATH_GDB, layer=layer_alvo, rows=50, ignore_geometry=True)
        
        print("\n📋 TODAS AS COLUNAS DISPONÍVEIS:")
        print(df.columns.tolist())

        # 4. Busca por Colunas de Energia
        cols_energia = [c for c in df.columns if 'ENE' in c or 'KWH' in c or 'CONS' in c]
        
        print(f"\n⚡ COLUNAS DE ENERGIA ENCONTRADAS: {cols_energia}")
        
        if cols_energia:
            col = cols_energia[0]
            print(f"\n🧪 AMOSTRA DA COLUNA '{col}':")
            print(f"   Tipo de dado detectado: {df[col].dtype}")
            print("   --- Primeiros 10 valores ---")
            print(df[col].head(10).to_string())
        else:
            print("⚠️ Nenhuma coluna com nome 'ENE', 'KWH' ou 'CONS' encontrada.")

    except Exception as e:
        print(f"Erro ao ler a tabela: {e}")

if __name__ == "__main__":
    inspecionar()