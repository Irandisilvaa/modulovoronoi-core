import geopandas as gpd
import pandas as pd
import os
import json
import warnings

warnings.filterwarnings('ignore')

NOME_PASTA_GDB = "Energisa_SE_6587_2023-12-31_V11_20250701-0833.gdb"
NOME_ARQUIVO_VORONOI = "subestacoes_logicas_aracaju.geojson"
NOME_ARQUIVO_SAIDA = "perfil_mercado_aracaju.json"

MAPA_CLASSES = {
    'RE': 'Residencial',
    'CO': 'Comercial',
    'IN': 'Industrial',
    'RU': 'Rural',
    'PP': 'Poder Público',
    'SP': 'Poder Público',
    'PO': 'Poder Público'
}

def calcular_consumo_real(df):
    """Soma ENE_01 a ENE_12 convertendo erros para 0."""
    cols_energia = [f'ENE_{i:02d}' for i in range(1, 13)]
    cols_existentes = [c for c in cols_energia if c in df.columns]
    
    if not cols_existentes:
        df['CONSUMO_ANUAL'] = 0.0
        return df

    for col in cols_existentes:
        df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0.0)
    
    df['CONSUMO_ANUAL'] = df[cols_existentes].sum(axis=1)
    return df

def analisar_mercado():
    print("INICIANDO ANALISE DETALHADA (POR ID)...")
    
    dir_script = os.path.dirname(os.path.abspath(__file__))
    dir_raiz = os.path.dirname(os.path.dirname(dir_script))
    
    path_voronoi = os.path.join(dir_raiz, NOME_ARQUIVO_VORONOI)
    path_gdb = os.path.join(dir_raiz, "dados", NOME_PASTA_GDB)
    path_saida = os.path.join(dir_raiz, NOME_ARQUIVO_SAIDA)

    # 1. CARREGAR VORONOI
    print("1. Carregando territorios...")
    if not os.path.exists(path_voronoi):
        # Fallback para pasta atual
        if os.path.exists(NOME_ARQUIVO_VORONOI):
            path_voronoi = NOME_ARQUIVO_VORONOI
        else:
            print(f"ERRO: Voronoi não encontrado em {path_voronoi}")
            return

    try:
        gdf_voronoi = gpd.read_file(path_voronoi).to_crs(epsg=31984)
        if 'COD_ID' not in gdf_voronoi.columns:
            print("ERRO CRÍTICO: Voronoi sem coluna COD_ID.")
            return
    except Exception as e:
        print(f"Erro Voronoi: {e}")
        return

    # 2. MAPEANDO TRAFOS 
    print("2. Mapeando Transformadores...")
    try:
        gdf_trafos = gpd.read_file(path_gdb, layer='UNTRMT', engine='pyogrio').to_crs(epsg=31984)
        
        # O sjoin cria sufixos _left e _right se houver colunas iguais (COD_ID)
        trafos_join = gpd.sjoin(gdf_trafos, gdf_voronoi[['NOM', 'COD_ID', 'geometry']], predicate="intersects")
        
        # Tratamento do conflito de nomes
        if 'COD_ID_right' in trafos_join.columns:
            trafos_join = trafos_join.rename(columns={'COD_ID_right': 'ID_SUBESTACAO'})
        
        if 'COD_ID_left' in trafos_join.columns:
            trafos_join = trafos_join.rename(columns={'COD_ID_left': 'COD_ID'})
        
        if 'NOM' in trafos_join.columns:
            trafos_join = trafos_join.rename(columns={'NOM': 'NOME_SUBESTACAO'})
        elif 'NOM_right' in trafos_join.columns:
            trafos_join = trafos_join.rename(columns={'NOM_right': 'NOME_SUBESTACAO'})
            
        # Garante que temos as colunas necessárias
        cols_necessarias = ['COD_ID', 'NOME_SUBESTACAO', 'ID_SUBESTACAO']
        for col in cols_necessarias:
            if col not in trafos_join.columns:
                print(f"ERRO: Coluna {col} não encontrada após o join. Colunas disponíveis: {trafos_join.columns.tolist()}")
                return

        ref_trafos = trafos_join[cols_necessarias].copy()
        ref_trafos['COD_ID'] = ref_trafos['COD_ID'].astype(str)
        
        print(f"   -> {len(ref_trafos)} transformadores vinculados.")

    except Exception as e:
        print(f"Erro Crítico em Transformadores: {e}")
        import traceback
        traceback.print_exc()
        return

    # 3. CONSUMIDORES
    print("3. Processando Consumidores...")
    df_cons_final = pd.DataFrame()
    mapa_pn_classe = {}
    
    try:
        cols_ene = [f'ENE_{i:02d}' for i in range(1, 13)]
        cols_leitura = ['UNI_TR_MT', 'CLAS_SUB', 'PN_CON'] + cols_ene
        
        gdf_uc = gpd.read_file(path_gdb, layer='UCBT_tab', engine='pyogrio', columns=cols_leitura)
        df_uc = pd.DataFrame(gdf_uc).drop(columns='geometry', errors='ignore')
        
        df_uc = calcular_consumo_real(df_uc)
        df_uc['UNI_TR_MT'] = df_uc['UNI_TR_MT'].astype(str)
        
        df_cons_final = pd.merge(df_uc, ref_trafos, left_on='UNI_TR_MT', right_on='COD_ID', how='inner')
        df_cons_final['TIPO'] = df_cons_final['CLAS_SUB'].str[:2].map(MAPA_CLASSES).fillna('Outros')
        
        mapa_pn_classe = df_cons_final[['PN_CON', 'TIPO']].drop_duplicates(subset='PN_CON').set_index('PN_CON')['TIPO']
    except Exception as e:
        print(f"Erro Consumidores: {e}")

    # 4. GERAÇÃO DISTRIBUÍDA
    print("4. Processando GD...")
    df_gd_final = pd.DataFrame()
    try:
        gdf_gd = gpd.read_file(path_gdb, layer='UGBT_tab', engine='pyogrio', columns=['UNI_TR_MT', 'POT_INST', 'PN_CON'])
        df_gd = pd.DataFrame(gdf_gd).drop(columns='geometry', errors='ignore')
        df_gd['POT_INST'] = pd.to_numeric(df_gd['POT_INST'], errors='coerce').fillna(0.0)
        df_gd['UNI_TR_MT'] = df_gd['UNI_TR_MT'].astype(str)
        
        df_gd_final = pd.merge(df_gd, ref_trafos, left_on='UNI_TR_MT', right_on='COD_ID', how='inner')
        
        if not mapa_pn_classe.empty:
            df_gd_final['TIPO'] = df_gd_final['PN_CON'].map(mapa_pn_classe).fillna('Outros')
        else:
            df_gd_final['TIPO'] = 'Outros'
    except Exception as e:
        print(f"Aviso GD: {e}")

    # 5. GERAR JSON
    print("5. Salvando JSON...")
    relatorio = []
    
    ids_cons = set(df_cons_final['ID_SUBESTACAO'].unique()) if not df_cons_final.empty else set()
    ids_gd = set(df_gd_final['ID_SUBESTACAO'].unique()) if not df_gd_final.empty else set()
    ids_unicos = sorted(list([x for x in (ids_cons | ids_gd) if str(x) != 'nan']))

    for sub_id in ids_unicos:
        d_cons = df_cons_final[df_cons_final['ID_SUBESTACAO'] == sub_id] if not df_cons_final.empty else pd.DataFrame()
        d_gd = df_gd_final[df_gd_final['ID_SUBESTACAO'] == sub_id] if not df_gd_final.empty else pd.DataFrame()
        
        nome = "Desconhecido"
        if not d_cons.empty: nome = d_cons.iloc[0]['NOME_SUBESTACAO']
        elif not d_gd.empty: nome = d_gd.iloc[0]['NOME_SUBESTACAO']
        
        geom_dict = None
        try:
            row = gdf_voronoi[gdf_voronoi['COD_ID'] == sub_id]
            if not row.empty: geom_dict = json.loads(row.iloc[0].geometry.json)
        except: pass

        consumo = d_cons['CONSUMO_ANUAL'].sum() if not d_cons.empty else 0
        potencia = d_gd['POT_INST'].sum() if not d_gd.empty else 0
        
        nivel = "BAIXO"
        if potencia > 1000: nivel = "MEDIO"
        if potencia > 5000: nivel = "ALTO"

        stats = {
            "subestacao": f"{nome} (ID: {sub_id})",
            "id_tecnico": str(sub_id),
            "metricas_rede": {
                "total_clientes": len(d_cons),
                "consumo_anual_mwh": float(round(consumo/1000, 2)),
                "nivel_criticidade_gd": nivel
            },
            "geracao_distribuida": {
                "total_unidades": len(d_gd),
                "potencia_total_kw": float(round(potencia, 2)),
                "detalhe_por_classe": {}
            },
            "perfil_consumo": {},
            "geometry": geom_dict
        }
        
        for cls in ['Residencial', 'Comercial', 'Industrial', 'Rural', 'Poder Público']:
            df_c = d_cons[d_cons['TIPO'] == cls] if not d_cons.empty else pd.DataFrame()
            if len(df_c) > 0:
                c_cls = df_c['CONSUMO_ANUAL'].sum()
                stats["perfil_consumo"][cls] = {
                    "qtd_clientes": len(df_c),
                    "pct": round((c_cls/consumo*100) if consumo > 0 else 0, 1),
                    "consumo_anual_mwh": float(round(c_cls/1000, 2))
                }
            
            p_gd = d_gd[d_gd['TIPO'] == cls]['POT_INST'].sum() if not d_gd.empty else 0
            if p_gd > 0:
                stats["geracao_distribuida"]["detalhe_por_classe"][cls] = float(round(p_gd, 2))
        
        relatorio.append(stats)

    with open(path_saida, 'w', encoding='utf-8') as f:
        json.dump(relatorio, f, indent=4, ensure_ascii=False)
    
    print(f"SUCESSO: Arquivo salvo em {path_saida}")

def garantir_mercado_atualizado():
    dir_script = os.path.dirname(os.path.abspath(__file__))
    dir_raiz = os.path.dirname(os.path.dirname(dir_script))
    path_saida = os.path.join(dir_raiz, NOME_ARQUIVO_SAIDA)

    if not os.path.exists(path_saida):
        analisar_mercado()
    return path_saida

if __name__ == "__main__":
    analisar_mercado()