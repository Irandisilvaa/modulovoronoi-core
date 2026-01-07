import geopandas as gpd
import pandas as pd
import os
import traceback
import sys

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

from config import PATH_GDB

def normalizar_id(valor):
    """
    Remove pontos decimais e espaços para garantir comparação segura.
    Ex: 123.0 -> "123" | " 123 " -> "123" | 123 -> "123"
    """
    if pd.isna(valor):
        return ""
    s = str(valor).strip()
    if s.endswith('.0'):
        return s[:-2]
    return s

def buscar_dados_reais_para_ia(nome_subestacao):
    """
    Lê o GDB e retorna a soma bruta da energia dos consumidores vinculados.
    RETORNO: Sempre em kWh (escala fixa).
    """
    print(f"\n🤖 ETL IA: Iniciando varredura para '{nome_subestacao}' (Modo Fixo kWh)...")
    
    if not os.path.exists(PATH_GDB):
        print(f"❌ GDB não encontrado em: {PATH_GDB}")
        return gerar_fallback(nome_subestacao)

    try:

        print("   📂 Lendo camada SUB...")
        try:
            # Tenta ler apenas colunas essenciais para ser mais rápido e gastar menos memória
            sample_sub = gpd.read_file(PATH_GDB, layer='SUB', engine='pyogrio', rows=1)
            cols_todas = sample_sub.columns.tolist()
            
            # Identifica colunas dinamicamente (para funcionar em bases com nomes diferentes)
            col_nome = next((c for c in cols_todas if c.upper() in ['NOM', 'NOME', 'NAME', 'PAC_1']), None)
            col_id   = next((c for c in cols_todas if c.upper() in ['COD_ID', 'ID', 'CODIGO', 'SUB']), None)
            
            if not col_nome or not col_id:
                print(f"❌ Colunas de ID/Nome não identificadas. Disp: {cols_todas}")
                return gerar_fallback(nome_subestacao)

            gdf_sub = gpd.read_file(PATH_GDB, layer='SUB', engine='pyogrio', columns=[col_nome, col_id])
            
        except Exception as e:
            print(f"❌ Erro ao ler layer SUB: {e}")
            return gerar_fallback(nome_subestacao)

        filtro = gdf_sub[col_nome].astype(str).str.upper().str.contains(str(nome_subestacao).strip().upper(), na=False)
        
        if filtro.sum() == 0:
            print(f"❌ Subestação '{nome_subestacao}' não encontrada na lista de nomes.")
            # Debug: Mostra alguns nomes disponíveis para ajudar
            print(f"   (Exemplos no GDB: {gdf_sub[col_nome].head(3).tolist()})")
            return gerar_fallback(nome_subestacao)
            
        dados_sub = gdf_sub[filtro].iloc[0]
        id_sub_original = dados_sub[col_id]
        id_sub_str = normalizar_id(id_sub_original) # Normaliza ID alvo para busca
        nome_real = dados_sub[col_nome]
        
        print(f"   📍 Alvo Identificado: {nome_real}")
        print(f"   🔑 ID Original: {id_sub_original} | ID Normalizado: '{id_sub_str}'")
        
        print(f"   🔍 Lendo base de consumidores (UCBT)... processando carga.")
        
        try:
            layers = gpd.list_layers(PATH_GDB)['name'].tolist()
            # Tenta achar a layer correta, as vezes muda o nome
            layer_consumidor = 'UCBT' if 'UCBT' in layers else 'UCBT_tab'
            
            # Otimização: Ler apenas colunas necessárias
            cols_uc_all = gpd.read_file(PATH_GDB, layer=layer_consumidor, engine='pyogrio', rows=1).columns.tolist()
            
            # Identificar colunas de energia (ENE_01, ENE_02...) e classe
            cols_ene = [c for c in cols_uc_all if c.upper().startswith('ENE_')]
            col_classe = next((c for c in cols_uc_all if c in ['CLA_CONS', 'TIP_CC', 'CLASSE', 'COD_CLASS']), None)
            
            cols_to_read = ['SUB'] + cols_ene
            if col_classe: cols_to_read.append(col_classe)
            
            # Leitura Otimizada
            df_uc = gpd.read_file(
                PATH_GDB, 
                layer=layer_consumidor, 
                engine='pyogrio', 
                ignore_geometry=True,
                columns=cols_to_read
            )
        except Exception as e:
            print(f"❌ Erro ao ler UCBT: {e}")
            return gerar_fallback(nome_real)
        
        if 'SUB' not in df_uc.columns:
            print("⚠️ Tabela UCBT não tem coluna 'SUB'.")
            return gerar_fallback(nome_real)

        # Normaliza a coluna SUB do UCBT para comparar com o ID da Subestação
        df_uc['SUB_STR'] = df_uc['SUB'].apply(normalizar_id)

        clientes = df_uc[df_uc['SUB_STR'] == id_sub_str].copy()
        
        qtd_clientes = len(clientes)
        print(f"   👥 Clientes encontrados: {qtd_clientes}")

        if clientes.empty:
            print(f"⚠️ A subestação existe, mas nenhum cliente deu match no ID '{id_sub_str}'.")
            return gerar_fallback(nome_real)

        print("   🧮 Calculando DNA do perfil...")
        perfil_mix = {"residencial": 0.0, "comercial": 0.0, "industrial": 0.0, "rural": 0.0}

        total_sub = None
        
        if col_classe:
            # Soma total de energia de todos os clientes para calcular porcentagens
            clientes['total_ano'] = clientes[cols_ene].sum(axis=1)
            total_sub = clientes['total_ano'].sum()
            
            if total_sub > 0:
                agrupado = clientes.groupby(col_classe)['total_ano'].sum()
                
                for classe_cod, energia in agrupado.items():
                    pct = energia / total_sub
                    c_str = str(classe_cod).upper()
                    
                    # Lógica de mapeamento Aneel simplificada
                    if c_str == '1' or 'RES' in c_str:
                        perfil_mix['residencial'] += pct
                    elif c_str == '3' or 'COM' in c_str:
                        perfil_mix['comercial'] += pct
                    elif c_str in ['2', '8'] or 'IND' in c_str:
                        perfil_mix['industrial'] += pct
                    elif c_str == '4' or 'RUR' in c_str:
                        perfil_mix['rural'] += pct
                    else:
                        perfil_mix['comercial'] += pct # Outros cai em comercial
            else:
                print("   ⚠️ total_sub igual a zero -> não foi possível calcular percentual por classes a partir dos dados. Será usado perfil padrão.")
              
                perfil_mix = {"residencial": 0.4, "comercial": 0.3, "industrial": 0.3, "rural": 0.0}
        else:
            print("   ⚠️ Sem coluna de classe, usando perfil misto padrão.")
            perfil_mix = {"residencial": 0.4, "comercial": 0.3, "industrial": 0.3, "rural": 0.0}

       
        soma_mix = sum(perfil_mix.values())
        if soma_mix <= 0:
            perfil_mix = {"residencial": 0.4, "comercial": 0.3, "industrial": 0.3, "rural": 0.0}
            soma_mix = sum(perfil_mix.values())
        if abs(soma_mix - 1.0) > 1e-6:
            # normalizar
            perfil_mix = {k: (v / soma_mix) for k, v in perfil_mix.items()}

        perfil_mensal = {}
        for col in cols_ene:
            try:
                parts = col.split('_')
                if len(parts) > 1 and parts[1].isdigit():
                    mes = int(parts[1])
                    val = clientes[col].sum() 
                    perfil_mensal[mes] = float(val)
            except:
                pass

        soma_perfil_mensal = sum(perfil_mensal.values()) if perfil_mensal else 0.0

        if soma_perfil_mensal <= 0:
            print("   ⚠️ Os valores mensais lidos estão vazios ou zerados.")
            if total_sub and total_sub > 0:
                valor_medio_mes = float(total_sub) / 12.0
                perfil_mensal = {i: valor_medio_mes for i in range(1,13)}
                print(f"   → Distribuindo total anual ({total_sub:,.0f} kWh) igualmente por mês: {valor_medio_mes:,.0f} kWh/mês")
            else:
                perfil_mensal = {i: 150000.0 for i in range(1,13)}
                print("   → Usando fallback padrão: 150000 kWh/mês para todos os meses.")

        print(f"✅ Sucesso! Dados (kWh) extraídos para {nome_real}")

        consumo_mensal_por_classe = {}
        for mes, val_mes in perfil_mensal.items():
            consumo_mensal_por_classe[mes] = {
                "residencial": float(val_mes * perfil_mix.get('residencial', 0.0)),
                "comercial":    float(val_mes * perfil_mix.get('comercial', 0.0)),
                "industrial":   float(val_mes * perfil_mix.get('industrial', 0.0)),
                "rural":        float(val_mes * perfil_mix.get('rural', 0.0))
            }

        return {
            "subestacao": nome_real,
            "id": int(id_sub_str) if id_sub_str.isdigit() else id_sub_str,
            "consumo_mensal": perfil_mensal,
            "consumo_mensal_por_classe": consumo_mensal_por_classe, 
            "dna_perfil": perfil_mix,        
            "origem": "BDGD Real"
        }

    except Exception as e:
        print(f"❌ Erro Crítico no ETL: {e}")
        traceback.print_exc()
        return gerar_fallback(nome_subestacao)

def gerar_fallback(nome):
    """
    Fallback com valores coerentes em kWh (números grandes) para não quebrar a escala do gráfico.
    """
    print(f"   ⚠️ ATIVANDO FALLBACK (Valores Estimados) PARA {nome}")
  
    return {
        "subestacao": nome, 
        "id": "FALLBACK",
        "consumo_mensal": {i: 150000.0 for i in range(1,13)},
        "dna_perfil": {"residencial": 0.5, "comercial": 0.3, "industrial": 0.2, "rural": 0.0},
        "alerta": True
    }
