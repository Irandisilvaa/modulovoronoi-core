import geopandas as gpd
import os

try:
    from config import PATH_GDB
except ImportError:
    PATH_GDB = r"C:\Users\irand\Documents\gridscope-core\data\raw\SE_2023.gdb"

def buscar_dados_reais_para_ia(nome_subestacao):
    print(f"\n🤖 IA: Analisando DNA da subestação '{nome_subestacao}'...")
    
    if not os.path.exists(PATH_GDB):
        return {"erro": "GDB não encontrado"}

    try:
        sample_sub = gpd.read_file(PATH_GDB, layer='SUB', engine='pyogrio', rows=1)
        cols_sub = sample_sub.columns
        
        col_nome_sub = next((c for c in cols_sub if c.upper() in ['NOM', 'NOME', 'NAME', 'PAC_1']), None)
        col_id_sub = next((c for c in cols_sub if c.upper() in ['COD_ID', 'ID', 'CODIGO', 'SUB']), None)
        
        if not col_nome_sub: return {"erro": "Coluna de nome da SUB não encontrada"}

        gdf_sub = gpd.read_file(PATH_GDB, layer='SUB', engine='pyogrio', columns=[col_nome_sub, col_id_sub])
        filtro = gdf_sub[col_nome_sub].str.upper().str.contains(nome_subestacao.strip().upper(), na=False)
        
        if filtro.sum() == 0:
            print(f"❌ Subestação '{nome_subestacao}' não encontrada no GDB.")
            return gerar_fallback(nome_subestacao)
            
        dados_sub = gdf_sub[filtro].iloc[0]
        id_sub = dados_sub[col_id_sub]
        nome_real = dados_sub[col_nome_sub]
        
        print(f"   📍 Alvo Identificado: {nome_real} (ID: {id_sub})")

        print(f"   🔍 Lendo base de consumidores (isso pode demorar um pouco)...")
        
        layers = gpd.list_layers(PATH_GDB)['name'].tolist()
        layer_consumidor = 'UCBT'
        if 'UCBT_tab' in layers: layer_consumidor = 'UCBT_tab'
        
        df_uc = gpd.read_file(PATH_GDB, layer=layer_consumidor, engine='pyogrio', ignore_geometry=True)
        
        if 'SUB' in df_uc.columns:
            clientes = df_uc[df_uc['SUB'] == id_sub].copy()
        else:
            print("⚠️ Aviso: Tabela UCBT não tem coluna 'SUB' direta. Usando Fallback.")
            return gerar_fallback(nome_real)

        if clientes.empty:
            print("⚠️ Aviso: Nenhum consumidor encontrado vinculado a este ID.")
            return gerar_fallback(nome_real)

        possiveis_colunas_classe = ['CLA_CONS', 'TIP_CC', 'CLASSE', 'DESCR_CLASSE', 'COD_CLASS']
        col_classe = next((c for c in clientes.columns if c in possiveis_colunas_classe), None)
        
        if not col_classe:
            print(f"❌ Erro: Não encontrei coluna de classe (ex: CLA_CONS). Colunas disp: {list(clientes.columns[:10])}...")
            return gerar_fallback(nome_real)

        print(f"   ✅ Coluna de Classe encontrada: {col_classe}")

        cols_ene = [c for c in clientes.columns if c.startswith('ENE_')]
        if not cols_ene:
             print("❌ Erro: Colunas de energia ENE_01... não encontradas.")
             return gerar_fallback(nome_real)

        clientes['total_ano'] = clientes[cols_ene].sum(axis=1)
        
        mix = clientes.groupby(col_classe)['total_ano'].sum()
        total_energia = mix.sum()
        
        perfil_mix = {"residencial": 0.0, "comercial": 0.0, "industrial": 0.0, "rural": 0.0}
        
        if total_energia > 0:
            for classe_raw, valor in mix.items():
                pct = valor / total_energia
                classe_str = str(classe_raw).upper()
                
                if classe_str in ['1', 'RE', 'RESIDENCIAL']:
                    perfil_mix['residencial'] += pct
                elif classe_str in ['2', 'CO', 'COMERCIAL', 'SERVICO_PUBLICO']: 
                    perfil_mix['comercial'] += pct
                elif classe_str in ['3', 'IN', 'INDUSTRIAL']: 
                    perfil_mix['industrial'] += pct
                elif classe_str in ['4', 'RU', 'RURAL']: 
                    perfil_mix['rural'] += pct
                else:
                    perfil_mix['comercial'] += pct

        print(f"   🧬 DNA Calculado: Ind={perfil_mix['industrial']:.1%} | Res={perfil_mix['residencial']:.1%} | Com={perfil_mix['comercial']:.1%}")

        perfil_mensal = {}
        for i in range(1, 13):
            col = f"ENE_{i:02d}"
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
        traceback.print_exc()
        return gerar_fallback(nome_subestacao)

def gerar_fallback(nome):
    """Retorna um perfil padrão para não travar o gráfico"""
    print(f"   ⚠️ Usando Perfil Genérico (Fallback) para {nome}")
    return {
        "subestacao": nome, 
        "id": "FALLBACK",
        "consumo_mensal": {i: 500 for i in range(1,13)},
        "dna_perfil": {"residencial": 0.6, "comercial": 0.3, "industrial": 0.1, "rural": 0.0},
        "alerta": True
    }