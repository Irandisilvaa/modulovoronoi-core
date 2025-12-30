import sys
import os
import geopandas as gpd
import pandas as pd
import json
import warnings


sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import PATH_GDB, PATH_GEOJSON, PATH_JSON_MERCADO

warnings.filterwarnings('ignore')

MAPA_CLASSES = {
    'RE': 'Residencial',
    'CO': 'Comercial',
    'IN': 'Industrial',
    'RU': 'Rural',
    'PP': 'Poder Público'
}

def analisar_mercado():
    print("INICIANDO ANALISE DETALHADA (POR CLASSE)...")
    
    path_voronoi = PATH_GEOJSON
    path_gdb = PATH_GDB
    path_saida = PATH_JSON_MERCADO

    if not os.path.exists(path_voronoi):
        print(f"Erro: Voronoi não encontrado em {path_voronoi}")
        return

    # 1. Carregar Voronoi
    print("1. Carregando territorios...")
    try:
        gdf_voronoi = gpd.read_file(path_voronoi).to_crs(epsg=31984)
    except Exception as e:
        print(f"Erro ao ler Voronoi: {e}")
        return

    # 2. Carregar Transformadores (GDB)
    print("2. Mapeando Transformadores...")
    try:
        gdf_trafos = gpd.read_file(path_gdb, layer='UNTRMT', engine='pyogrio').to_crs(epsg=31984)
        
        # Cruzamento Espacial: Qual trafo está dentro de qual polígono Voronoi?
        trafos_join = gpd.sjoin(gdf_trafos, gdf_voronoi[['NOM', 'geometry']], predicate="intersects")
        
        # Tabela de Referência: ID do Trafo -> Nome da Subestação
        ref_trafos = trafos_join[['COD_ID', 'NOM']].copy()
        ref_trafos['COD_ID'] = ref_trafos['COD_ID'].astype(str)
        
    except Exception as e:
        print(f"Erro ao ler transformadores: {e}")
        return

    # 3. PROCESSAR CONSUMO (UCBT)
    print("3. Processando Consumidores...")
    try:
        gdf_uc = gpd.read_file(path_gdb, layer='UCBT_tab', engine='pyogrio', columns=['UNI_TR_MT', 'CLAS_SUB', 'ENE_12', 'PN_CON'])
        df_uc = pd.DataFrame(gdf_uc).drop(columns='geometry', errors='ignore')
        df_uc['UNI_TR_MT'] = df_uc['UNI_TR_MT'].astype(str)
        
        df_cons_final = pd.merge(df_uc, ref_trafos, left_on='UNI_TR_MT', right_on='COD_ID', how='inner')
        
        df_cons_final['TIPO'] = df_cons_final['CLAS_SUB'].str[:2].map(MAPA_CLASSES).fillna('Outros')
        
        mapa_pn_classe = df_cons_final[['PN_CON', 'TIPO']].drop_duplicates(subset='PN_CON').set_index('PN_CON')['TIPO']
        
    except Exception as e:
        print(f"Erro consumidores: {e}")
        return

    # 4. PROCESSAR GERACAO DISTRIBUIDA (UGBT)
    print("4. Processando Paineis Solares...")
    try:
        gdf_gd = gpd.read_file(path_gdb, layer='UGBT_tab', engine='pyogrio', columns=['UNI_TR_MT', 'POT_INST', 'PN_CON'])
        df_gd = pd.DataFrame(gdf_gd).drop(columns='geometry', errors='ignore')
        df_gd['UNI_TR_MT'] = df_gd['UNI_TR_MT'].astype(str)
        
        df_gd_final = pd.merge(df_gd, ref_trafos, left_on='UNI_TR_MT', right_on='COD_ID', how='inner')
        
        df_gd_final['TIPO'] = df_gd_final['PN_CON'].map(mapa_pn_classe).fillna('Outros')
        
        print(f"   -> {len(df_gd_final)} usinas mapeadas.")
        
    except Exception as e:
        print(f"Aviso GD (pode estar vazio): {e}")
        df_gd_final = pd.DataFrame(columns=['NOM', 'POT_INST', 'TIPO'])

    # 5. CONSOLIDAR RELATORIO
    print("5. Gerando JSON Detalhado...")
    relatorio = []
    
    todas_subs = sorted(list(set(df_cons_final['NOM'].unique()) | set(df_gd_final['NOM'].unique())))

    for sub in todas_subs:
        dados_cons = df_cons_final[df_cons_final['NOM'] == sub]
        dados_gd = df_gd_final[df_gd_final['NOM'] == sub]
        
        total_clientes = len(dados_cons)
        consumo_total = dados_cons['ENE_12'].sum() if not dados_cons.empty else 0
        qtd_gd_total = len(dados_gd)
        potencia_gd_total = dados_gd['POT_INST'].sum() if not dados_gd.empty else 0
        
        nivel_criticidade = "BAIXO"
        if potencia_gd_total > 1000: nivel_criticidade = "MEDIO"
        if potencia_gd_total > 5000: nivel_criticidade = "ALTO"

        stats = {
            "subestacao": sub,
            "metricas_rede": {
                "total_clientes": int(total_clientes),
                "consumo_anual_mwh": float(round(consumo_total/1000, 2)),
                "nivel_criticidade_gd": nivel_criticidade
            },
            "geracao_distribuida": {
                "total_unidades": int(qtd_gd_total),
                "potencia_total_kw": float(round(potencia_gd_total, 2)),
                "detalhe_por_classe": {}
            },
            "perfil_consumo": {}
        }
        
        classes_analise = ['Residencial', 'Comercial', 'Industrial', 'Rural', 'Poder Público', 'Outros']
        
        for cls in classes_analise:
            qtd_cli = int(dados_cons[dados_cons['TIPO'] == cls].shape[0])
            if qtd_cli > 0:
                stats["perfil_consumo"][cls] = {
                    "qtd_clientes": qtd_cli,
                    "pct": round((qtd_cli/total_clientes)*100, 1)
                }
            
            pot_classe = dados_gd[dados_gd['TIPO'] == cls]['POT_INST'].sum()
            if pot_classe > 0:
                stats["geracao_distribuida"]["detalhe_por_classe"][cls] = float(round(pot_classe, 2))
        
        relatorio.append(stats)

    with open(path_saida, 'w', encoding='utf-8') as f:
        json.dump(relatorio, f, indent=4, ensure_ascii=False)
        
    print(f"SUCESSO! Relatorio atualizado em: {path_saida}")

if __name__ == "__main__":
    analisar_mercado()