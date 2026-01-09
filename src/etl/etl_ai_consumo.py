
import os
import sys
import pandas as pd
from typing import Dict, Any

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

def buscar_dados_reais_para_ia(nome_subestacao: str) -> Dict[str, Any]:

    print(f"\n🤖 ETL IA: Iniciando varredura DB para '{nome_subestacao}'...")
    
    try:
        from database import carregar_subestacoes, get_engine
        
        gdf_subs = carregar_subestacoes()
        
        filtro = gdf_subs['NOME'].str.upper().str.contains(nome_subestacao.strip().upper(), na=False)
        
        if filtro.sum() == 0:
            print(f"❌ Subestação '{nome_subestacao}' não encontrada na tabela 'subestacoes'.")
            return gerar_fallback(nome_subestacao)
            
        dados_sub = gdf_subs[filtro].iloc[0]
        id_sub = str(dados_sub['COD_ID'])
        nome_real = dados_sub['NOME']
        
        print(f"   📍 Alvo Identificado no Banco: {nome_real} (ID: {id_sub})")

        print(f"   🔍 Executando Query SQL Aggregation...")
        
        engine = get_engine()
        
        # Query otimizada: Soma energias agrupadas por classe
        sql = f"""
            SELECT 
                c."CLAS_SUB",
                SUM(c."ENE_01") as "ENE_01", SUM(c."ENE_02") as "ENE_02", SUM(c."ENE_03") as "ENE_03",
                SUM(c."ENE_04") as "ENE_04", SUM(c."ENE_05") as "ENE_05", SUM(c."ENE_06") as "ENE_06",
                SUM(c."ENE_07") as "ENE_07", SUM(c."ENE_08") as "ENE_08", SUM(c."ENE_09") as "ENE_09",
                SUM(c."ENE_10") as "ENE_10", SUM(c."ENE_11") as "ENE_11", SUM(c."ENE_12") as "ENE_12"
            FROM consumidores c
            JOIN transformadores t ON c."UNI_TR_MT" = t."COD_ID"
            WHERE t."SUB" = '{id_sub}'
            GROUP BY c."CLAS_SUB"
        """
        
        df_agregado = pd.read_sql(sql, engine)
        engine.dispose()
        
        if df_agregado.empty:
            print("⚠️ Aviso: Nenhum consumidor encontrado no Banco para esta SUB.")
            return gerar_fallback(nome_real)

        # 3. Processar Resultados
        cols_ene = [f'ENE_{i:02d}' for i in range(1, 13)]
        total_energia_ano = df_agregado[cols_ene].sum().sum()
        
        perfil_mix = {"residencial": 0.0, "comercial": 0.0, "industrial": 0.0, "rural": 0.0}
        
        # Agrupa classes brutas nas 4 categorias
        for idx, row in df_agregado.iterrows():
            classe_cod = str(row['CLAS_SUB']).strip()
            cons_ano = row[cols_ene].sum()
            pct = cons_ano / total_energia_ano if total_energia_ano > 0 else 0
            
            if classe_cod.startswith('1') or 'RES' in classe_cod: cat = 'residencial'
            elif classe_cod.startswith('2') or 'COM' in classe_cod: cat = 'comercial'
            elif classe_cod.startswith('3') or 'IND' in classe_cod: cat = 'industrial'
            elif classe_cod.startswith('4') or 'RUR' in classe_cod: cat = 'rural'
            else: cat = 'comercial' # Default
            
            perfil_mix[cat] += pct
        
        # Perfil Mensal Total
        perfil_mensal = {}
        for i in range(1, 13):
            col = f"ENE_{i:02d}"
            val_mwh = df_agregado[col].sum() / 1000.0 # Converte kWh -> MWh
            perfil_mensal[i] = val_mwh

        print(f"   🧬 DNA Calculado (SQL): Ind={perfil_mix['industrial']:.1%} | Res={perfil_mix['residencial']:.1%}")

        return {
            "subestacao": nome_real,
            "id": id_sub,
            "consumo_mensal": perfil_mensal,
            "dna_perfil": perfil_mix,
            "origem": "PostgreSQL (Real)"
        }

    except Exception as e:
        print(f"❌ Erro Crítico no ETL Banco: {e}")
        import traceback
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
