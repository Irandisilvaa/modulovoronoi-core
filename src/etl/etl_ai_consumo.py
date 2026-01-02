import pandas as pd
import geopandas as gpd
import os
import sys
import random
import time

# --- CONFIGURAÇÃO DE CAMINHOS ---
# Tenta importar o caminho do config, ou usa manual
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
try:
    from config import PATH_GDB
except ImportError:
    # Ajuste este caminho se necessário
    PATH_GDB = r"C:\Users\irand\Documents\gridscope-core\data\raw\SE_2023.gdb"

def buscar_dados_reais_para_ia(nome_subestacao):
    """
    Função Robusta para IA:
    1. Tenta encontrar a SUB e seus Circuitos (CTMT).
    2. Tenta encontrar Clientes (UCBT) ligados a esses Circuitos.
    3. Retorna o perfil MENSAL detalhado para alimentar a sazonalidade da IA.
    """
    print(f"\n🤖 IA: Buscando dados reais no BDGD para '{nome_subestacao}'...")
    
    if not os.path.exists(PATH_GDB):
        return {"erro": "Arquivo GDB não encontrado."}

    try:
        # --- PASSO 1: Descobrir o ID da Subestação ---
        # Lê apenas colunas essenciais para ser rápido
        gdf_sub = gpd.read_file(PATH_GDB, layer='SUB', engine='pyogrio', columns=['NOM', 'COD_ID'])
        
        # Normaliza nomes para busca
        nome_alvo_norm = nome_subestacao.strip().upper()
        
        # Filtra a subestação pelo nome
        filtro = gdf_sub['NOM'].str.upper().str.contains(nome_alvo_norm, na=False)
        sub_encontrada = gdf_sub[filtro]
        
        if sub_encontrada.empty:
            print(f"   ⚠️ Subestação '{nome_subestacao}' não achada. Usando fallback.")
            return gerar_estimativa_fallback(nome_subestacao)
        
        id_sub = sub_encontrada.iloc[0]['COD_ID']
        nome_real = sub_encontrada.iloc[0]['NOM']
        print(f"   ✅ Subestação localizada: {nome_real} (ID: {id_sub})")

        # --- PASSO 2: Achar os Alimentadores (CTMT) ---
        # A "Ponte": Subestação -> CTMT -> Cliente
        print("   🔍 Mapeando circuitos (CTMT) da subestação...")
        
        try:
            # Tenta ler a camada de circuitos
            gdf_ctmt = gpd.read_file(PATH_GDB, layer='CTMT', engine='pyogrio', columns=['COD_ID', 'SUB'])
            
            # Pega todos os circuitos que têm o ID da nossa Subestação
            circuitos = gdf_ctmt[gdf_ctmt['SUB'] == id_sub]['COD_ID'].unique()
            print(f"   🔗 Encontrados {len(circuitos)} alimentadores conectados.")
        except Exception:
            print("   ⚠️ Camada CTMT não encontrada ou erro de leitura. Tentando link direto...")
            circuitos = []

        # --- PASSO 3: Somar Consumo dos Clientes (UCBT) ---
        print("   ⏳ Lendo tabela de consumidores (pode demorar)...")
        
        # Lê a tabela sem geometria (muito mais rápido)
        # Importante: Garantir que lemos as colunas de energia
        df_uc = gpd.read_file(PATH_GDB, layer='UCBT_tab', engine='pyogrio', ignore_geometry=True)
        
        clientes = pd.DataFrame()

        # TENTATIVA A: Via Circuitos (Mais correto)
        if len(circuitos) > 0 and 'CTMT' in df_uc.columns:
            clientes = df_uc[df_uc['CTMT'].isin(circuitos)]
        
        # TENTATIVA B: Link Direto (Caso raro, mas possível)
        if clientes.empty and 'SUB' in df_uc.columns:
            clientes = df_uc[df_uc['SUB'] == id_sub]

        qtd_clientes = len(clientes)
        
        # --- PASSO 4: Verificação e Fallback ---
        if qtd_clientes == 0:
            print(f"   ⚠️ Nenhum cliente encontrado via vínculo CTMT ou SUB.")
            return gerar_estimativa_fallback(nome_real)

        # --- PASSO 5: Extração Detalhada Mês a Mês (PARA A IA) ---
        print("   📊 Calculando perfil sazonal mensal...")
        
        perfil_mensal = {}
        total_anual = 0.0
        
        # Itera de 01 a 12 para pegar cada coluna ENE_XX
        for i in range(1, 13):
            mes_str = f"{i:02d}" # '01', '02', etc.
            coluna_alvo = f"ENE_{mes_str}"
            
            # Procura a coluna no dataframe (ignorando case sensitive)
            col_encontrada = next((c for c in df_uc.columns if c.upper() == coluna_alvo), None)
            
            if col_encontrada:
                # Soma e converte de kWh para MWh
                soma_mes_mwh = clientes[col_encontrada].sum() / 1000.0
                perfil_mensal[i] = soma_mes_mwh
                total_anual += soma_mes_mwh
            else:
                perfil_mensal[i] = 0.0

        print(f"   ✅ Dados extraídos! Jan: {perfil_mensal[1]:.1f} MWh ... Dez: {perfil_mensal[12]:.1f} MWh")

        return {
            "subestacao": nome_real,
            "total_clientes": qtd_clientes,
            "consumo_anual_mwh": float(total_anual),
            "consumo_mensal": perfil_mensal, # <--- O DADO IMPORTANTE ESTÁ AQUI
            "origem": "BDGD (Real)"
        }

    except Exception as e:
        print(f"   ❌ Erro crítico no ETL: {e}")
        return gerar_estimativa_fallback(nome_subestacao)

def gerar_estimativa_fallback(nome_sub):
    """
    Gera dados estatísticos plausíveis com sazonalidade simulada
    para não travar a aplicação quando o BDGD falha.
    """
    print("   🔄 Ativando modo de ESTIMATIVA (Fallback)...")
    
    clientes_est = random.randint(2500, 8000)
    base_kwh_cliente = 180.0 # Média residencial
    
    perfil_mensal = {}
    total_anual = 0.0
    
    for i in range(1, 13):
        # Cria uma curva de verão (Jan/Fev/Dez mais altos)
        fator_sazonal = 1.0
        if i in [12, 1, 2, 3]: fator_sazonal = 1.25
        elif i in [6, 7]: fator_sazonal = 0.9
        
        consumo_mes = (clientes_est * base_kwh_cliente * fator_sazonal) / 1000.0 # MWh
        perfil_mensal[i] = consumo_mes
        total_anual += consumo_mes
    
    return {
        "subestacao": nome_sub,
        "total_clientes": clientes_est,
        "consumo_anual_mwh": round(total_anual, 2),
        "consumo_mensal": perfil_mensal,
        "origem": "Estimado (Dados Indisponíveis)",
        "alerta": True
    }