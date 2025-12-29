import geopandas as gpd
import pandas as pd
import os
import sys
import json

# --- CONFIGURAÇÃO ---
NOME_PASTA_GDB = "Energisa_SE_6587_2023-12-31_V11_20250701-0833.gdb"
NOME_ARQUIVO_VORONOI = "subestacoes_logicas_aracaju.geojson"
NOME_ARQUIVO_SAIDA = "perfil_mercado_aracaju.json"

# Mapa simplificado (Sem Poder Público como pedido)
MAPA_CLASSES = {
    'RE': 'Residencial',
    'CO': 'Comercial',
    'IN': 'Industrial',
    'RU': 'Rural',
    # Os outros códigos cairão em 'Outros' e não serão destacados
}

def analisar_mercado():
    print("INICIANDO ANÁLISE DE MERCADO (Foco: Res/Com/Ind)")
    
# --- CONFIGURAÇÃO DE CAMINHOS (CORRIGIDO) ---
    # 1. Pega a pasta onde este script está (ex: .../src/modelos)
    dir_script = os.path.dirname(os.path.abspath(__file__))
    
    # 2. Sobe um nível para a pasta 'src'
    dir_src = os.path.dirname(dir_script)
    
    # 3. Sobe mais um nível para a 'Raiz do Projeto' (onde está o GeoJSON e a pasta dados)
    dir_raiz = os.path.dirname(dir_src)

    # Agora os caminhos apontam para o lugar certo
    caminho_voronoi = os.path.join(dir_raiz, NOME_ARQUIVO_VORONOI)
    caminho_gdb = os.path.join(dir_raiz, "dados", NOME_PASTA_GDB)
    caminho_saida = os.path.join(dir_raiz, NOME_ARQUIVO_SAIDA)

    # Debug: Mostra onde ele está procurando (para você ter certeza)
    print(f"Procurando arquivos na raiz: {dir_raiz}")

    # 1. Carregar Voronoi
    if not os.path.exists(caminho_voronoi):
        print("Erro: Arquivo Voronoi não encontrado.")
        return
    gdf_voronoi = gpd.read_file(caminho_voronoi).to_crs(epsg=31984)

    # 2. Carregar Transformadores (GeoPandas)
    print("Lendo Transformadores...")
    try:
        gdf_trafos = gpd.read_file(caminho_gdb, layer='UNTRMT', engine='pyogrio').to_crs(epsg=31984)
    except:
        print("Erro ao ler transformadores.")
        return

    # 3. Cruzar Trafo x Voronoi
    print("Localizando transformadores...")
    trafos_com_sub = gpd.sjoin(gdf_trafos, gdf_voronoi[['NOM', 'geometry']], how="inner", predicate="intersects")
    trafos_lookup = trafos_com_sub[['COD_ID', 'NOM']].copy()
    trafos_lookup['COD_ID'] = trafos_lookup['COD_ID'].astype(str)

    # 4. Carregar Consumidores (GeoPandas -> DataFrame)
    print("Lendo Consumidores...")
    cols_uc = ['UNI_TR_MT', 'CLAS_SUB', 'ENE_12']
    gdf_consumidores = gpd.read_file(caminho_gdb, layer='UCBT_tab', engine='pyogrio', columns=cols_uc)
    df_consumidores = pd.DataFrame(gdf_consumidores) # Tira a geometria para ficar leve
    df_consumidores['UNI_TR_MT'] = df_consumidores['UNI_TR_MT'].astype(str)

    # 5. Merge Final
    print("Consolidando dados...")
    df_completo = pd.merge(df_consumidores, trafos_lookup, left_on='UNI_TR_MT', right_on='COD_ID', how='inner')
    
    # Mapeia as classes
    df_completo['CLASSE_GERAL'] = df_completo['CLAS_SUB'].str[:2].map(MAPA_CLASSES).fillna('Outros')

    # 6. Estatísticas
    resultados = []
    for subestacao, dados_sub in df_completo.groupby('NOM'):
        total = len(dados_sub)
        contagem = dados_sub['CLASSE_GERAL'].value_counts()
        
        stats = {
            "subestacao": subestacao,
            "total_clientes_estimados": int(total),
            "perfil": {},
            "consumo_total_kwh_mes": float(round(dados_sub['ENE_12'].sum(), 2))
        }
        
        # AQUI MUDOU: Só pegamos o que interessa
        for classe in ['Residencial', 'Comercial', 'Industrial']:
            qtd = int(contagem.get(classe, 0))
            pct = round((qtd / total) * 100, 2) if total > 0 else 0
            stats["perfil"][classe] = {"qtd": qtd, "pct": pct}
            
        resultados.append(stats)

    with open(caminho_saida, 'w', encoding='utf-8') as f:
        json.dump(resultados, f, indent=4, ensure_ascii=False)
        
    print(f"Dados Prontos! Arquivo salvo em: {caminho_saida}")

if __name__ == "__main__":
    analisar_mercado()