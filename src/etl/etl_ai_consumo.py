import pandas as pd
import geopandas as gpd
import os
import sys

# Tenta importar caminho do config, senão usa padrão
try:
    from config import PATH_GDB
except ImportError:
    # Ajuste este caminho se necessário
    PATH_GDB = r"C:\Users\irand\Documents\gridscope-core\data\raw\SE_2023.gdb"

def buscar_dados_reais_para_ia(nome_subestacao):
    print(f"\n🤖 IA: Analisando DNA da subestação '{nome_subestacao}'...")
    
    if not os.path.exists(PATH_GDB):
        return {"erro": "GDB não encontrado"}

    try:
        # --- 1. IDENTIFICAÇÃO DA SUBESTAÇÃO ---
        # Lê apenas 1 linha para pegar nomes das colunas da camada SUB
        sample_sub = gpd.read_file(PATH_GDB, layer='SUB', engine='pyogrio', rows=1)
        cols_sub = sample_sub.columns
        
        # Acha dinamicamente a coluna de NOME e ID
        col_nome_sub = next((c for c in cols_sub if c.upper() in ['NOM', 'NOME', 'NAME', 'PAC_1']), None)
        col_id_sub = next((c for c in cols_sub if c.upper() in ['COD_ID', 'ID', 'CODIGO', 'SUB']), None)
        
        if not col_nome_sub: return {"erro": "Coluna de nome da SUB não encontrada"}

        # Busca a subestação específica
        gdf_sub = gpd.read_file(PATH_GDB, layer='SUB', engine='pyogrio', columns=[col_nome_sub, col_id_sub])
        filtro = gdf_sub[col_nome_sub].str.upper().str.contains(nome_subestacao.strip().upper(), na=False)
        
        if filtro.sum() == 0:
            print(f"❌ Subestação '{nome_subestacao}' não encontrada no GDB.")
            return gerar_fallback(nome_subestacao)
            
        dados_sub = gdf_sub[filtro].iloc[0]
        id_sub = dados_sub[col_id_sub] # O código da subestação (ex: 15, ARU, etc)
        nome_real = dados_sub[col_nome_sub]
        
        print(f"   📍 Alvo Identificado: {nome_real} (ID: {id_sub})")

        # --- 2. BUSCA DE CONSUMIDORES (UCBT) ---
        print(f"   🔍 Lendo base de consumidores (isso pode demorar um pouco)...")
        
        # Tenta descobrir qual tabela existe (UCBT_tab ou UCBT)
        layers = gpd.list_layers(PATH_GDB)['name'].tolist()
        layer_consumidor = 'UCBT'
        if 'UCBT_tab' in layers: layer_consumidor = 'UCBT_tab'
        
        # Tenta ler colunas para achar a de Classe
        # Não filtramos colunas no read_file para garantir que vamos pegar a certa, 
        # mas usamos ignore_geometry para ser rápido.
        df_uc = gpd.read_file(PATH_GDB, layer=layer_consumidor, engine='pyogrio', ignore_geometry=True)
        
        # Filtra apenas os clientes dessa subestação
        # A coluna que liga UCBT à SUB geralmente é 'SUB' ou 'CTMT' (que liga ao trafo)
        # Vamos assumir que existe uma coluna 'SUB' direta. Se não, precisaríamos cruzar com UNTR/CTMT (mais complexo).
        if 'SUB' in df_uc.columns:
            clientes = df_uc[df_uc['SUB'] == id_sub].copy()
        else:
            # Se não tiver coluna SUB direta na UCBT, retorna erro ou fallback
            # (Implementação completa exigiria cruzar UCBT -> UNTR -> SSDMT -> SUB)
            print("⚠️ Aviso: Tabela UCBT não tem coluna 'SUB' direta. Usando Fallback.")
            return gerar_fallback(nome_real)

        if clientes.empty:
            print("⚠️ Aviso: Nenhum consumidor encontrado vinculado a este ID.")
            return gerar_fallback(nome_real)

        # --- 3. CORREÇÃO DO ERRO 'CLA_CONS' ---
        # Procura qual é a coluna de classe de consumo
        possiveis_colunas_classe = ['CLA_CONS', 'TIP_CC', 'CLASSE', 'DESCR_CLASSE', 'COD_CLASS']
        col_classe = next((c for c in clientes.columns if c in possiveis_colunas_classe), None)
        
        if not col_classe:
            print(f"❌ Erro: Não encontrei coluna de classe (ex: CLA_CONS). Colunas disp: {list(clientes.columns[:10])}...")
            return gerar_fallback(nome_real)

        print(f"   ✅ Coluna de Classe encontrada: {col_classe}")

        # --- 4. CÁLCULO DO DNA (PERFIL) ---
        cols_ene = [c for c in clientes.columns if c.startswith('ENE_')]
        if not cols_ene:
             print("❌ Erro: Colunas de energia ENE_01... não encontradas.")
             return gerar_fallback(nome_real)

        # Soma total anual por cliente
        clientes['total_ano'] = clientes[cols_ene].sum(axis=1)
        
        # Agrupa pela coluna de classe encontrada dinamicamente
        mix = clientes.groupby(col_classe)['total_ano'].sum()
        total_energia = mix.sum()
        
        perfil_mix = {"residencial": 0.0, "comercial": 0.0, "industrial": 0.0, "rural": 0.0}
        
        if total_energia > 0:
            for classe_raw, valor in mix.items():
                pct = valor / total_energia
                # Normaliza para string para verificar
                classe_str = str(classe_raw).upper()
                
                # Regras de mapeamento (Códigos comuns ANEEL)
                # 1 = Residencial, 2 = Comercial, 3 = Industrial, 4 = Rural
                # Ou strings: 'RE', 'CO', 'IN', 'RU'
                if classe_str in ['1', 'RE', 'RESIDENCIAL']: 
                    perfil_mix['residencial'] += pct
                elif classe_str in ['2', 'CO', 'COMERCIAL', 'SERVICO_PUBLICO']: 
                    perfil_mix['comercial'] += pct
                elif classe_str in ['3', 'IN', 'INDUSTRIAL']: 
                    perfil_mix['industrial'] += pct
                elif classe_str in ['4', 'RU', 'RURAL']: 
                    perfil_mix['rural'] += pct
                else:
                    # Distribui o resto (iluminação pública, poder público) no comercial
                    perfil_mix['comercial'] += pct 

        print(f"   🧬 DNA Calculado: Ind={perfil_mix['industrial']:.1%} | Res={perfil_mix['residencial']:.1%} | Com={perfil_mix['comercial']:.1%}")

        # Consumo mensal médio da subestação (em MWh)
        perfil_mensal = {}
        for i in range(1, 13):
            col = f"ENE_{i:02d}"
            # Soma de todos os clientes, divide por 1000 para virar MWh
            val_mwh = clientes[col].sum() / 1000.0
            perfil_mensal[i] = val_mwh

        return {
            "subestacao": nome_real,
            "id": id_sub,
            "consumo_mensal": perfil_mensal,
            "dna_perfil": perfil_mix,
            "origem": "BDGD Real"
        }

    except Exception as e:
        print(f"❌ Erro Crítico no ETL: {e}")
        import traceback
        traceback.print_exc() # Mostra onde foi o erro
        return gerar_fallback(nome_subestacao)

def gerar_fallback(nome):
    """Retorna um perfil padrão para não travar o gráfico"""
    print(f"   ⚠️ Usando Perfil Genérico (Fallback) para {nome}")
    return {
        "subestacao": nome, 
        "id": "FALLBACK",
        "consumo_mensal": {i: 500 for i in range(1,13)}, # 500 MWh fixo
        "dna_perfil": {"residencial": 0.6, "comercial": 0.3, "industrial": 0.1, "rural": 0.0},
        "alerta": True
    }