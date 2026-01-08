import geopandas as gpd
import matplotlib.pyplot as plt
import osmnx as ox
import numpy as np
import os
import sys
from scipy.spatial import Voronoi
from shapely.geometry import Polygon
from shapely.ops import unary_union

from config import CIDADE_ALVO, CRS_PROJETADO, DIR_RAIZ
from etl.carregador_aneel import carregar_subestacoes
from database import salvar_voronoi

def voronoi_finite_polygons_2d(vor, radius=None):
    """
    Algoritmo matemático para reconstruir regiões de Voronoi finitas.
    (Mantido original, apenas limpeza de estilo)
    """
    if vor.points.shape[1] != 2:
        raise ValueError("Requires 2D input")
    
    new_regions = []
    new_vertices = vor.vertices.tolist()
    center = vor.points.mean(axis=0)
    
    if radius is None:
        radius = np.ptp(vor.points).max() * 2
    
    all_ridges = {}
    for (p1, p2), (v1, v2) in zip(vor.ridge_points, vor.ridge_vertices):
        all_ridges.setdefault(p1, []).append((p2, v1, v2))
        all_ridges.setdefault(p2, []).append((p1, v1, v2))

    for p1, region in enumerate(vor.point_region):
        vertices = vor.regions[region]
        if all(v >= 0 for v in vertices):
            new_regions.append(vertices)
            continue

        ridges = all_ridges[p1]
        new_region = [v for v in vertices if v >= 0]

        for p2, v1, v2 in ridges:
            if v2 < 0: v1, v2 = v2, v1
            if v1 >= 0: continue
            
            t = vor.points[p2] - vor.points[p1]
            t /= np.linalg.norm(t)
            n = np.array([-t[1], t[0]])
            
            midpoint = vor.points[[p1, p2]].mean(axis=0)
            direction = np.sign(np.dot(midpoint - center, n)) * n
            far_point = vor.vertices[v2] + direction * radius
            
            new_region.append(len(new_vertices))
            new_vertices.append(far_point.tolist())

        vs = np.asarray([new_vertices[v] for v in new_region])
        c = vs.mean(axis=0)
        angles = np.arctan2(vs[:,1] - c[1], vs[:,0] - c[0])
        new_region = np.array(new_region)[np.argsort(angles)]
        new_regions.append(new_region.tolist())

    return new_regions, np.asarray(new_vertices)

def main():
    print(f"--- INICIANDO GERAÇÃO DE TERRITÓRIOS (VORONOI) ---")
    print(f"Alvo: {CIDADE_ALVO}")
    
    subs_raw = carregar_subestacoes()
    print(f"Baixando limites geográficos via OpenStreetMap...")
    try:
        limite_cidade = ox.geocode_to_gdf(CIDADE_ALVO)
    except Exception as e:
        print(f"ERRO OSM: {e}")
        print("Verifique sua conexão ou o nome da cidade no .env")
        sys.exit(1)

    if subs_raw.crs is None:
        subs_raw.set_crs(epsg=4674, inplace=True)
    
    limite_cidade = limite_cidade.to_crs(subs_raw.crs)

    print("Filtrando subestações na malha urbana...")
    subs_cidade = gpd.clip(subs_raw, limite_cidade)
    print(f"   -> Encontradas: {len(subs_cidade)} subestações na área urbana.")
    
    print("Filtrando subestações com consumidores (em operação)...")
    try:
        from database import carregar_consumidores
        df_consumidores = carregar_consumidores(colunas=['UNI_TR_MT'], ignore_geometry=True)
        
        ids_trafos_com_consumo = set(df_consumidores['UNI_TR_MT'].dropna().unique())
        
        from database import carregar_transformadores
        df_trafos = carregar_transformadores(colunas=['COD_ID', 'SUB'])
        
        trafos_com_consumo = df_trafos[df_trafos['COD_ID'].isin(ids_trafos_com_consumo)]
        
        ids_subs_com_consumo = set(trafos_com_consumo['SUB'].dropna().astype(str).unique())
        
        subs_cidade['COD_ID'] = subs_cidade['COD_ID'].astype(str)
        total_antes = len(subs_cidade)
        subs_cidade = subs_cidade[subs_cidade['COD_ID'].isin(ids_subs_com_consumo)].copy()
        
        removidas = total_antes - len(subs_cidade)
        print(f"   -> Removidas {removidas} subestações sem consumidores (planejadas/sem carga)")
        print(f"   -> {len(subs_cidade)} subestações em operação.")
        
    except Exception as e:
        print(f"   ⚠️ Aviso: Não foi possível filtrar por consumidores: {e}")
        print(f"   -> Mantendo todas as {len(subs_cidade)} subestações urbanas.")
    
    if len(subs_cidade) < 2:
        print("ERRO: Menos de 2 subestações. Voronoi requer no mínimo 2 pontos.")
        sys.exit(1)

    subs_proj = subs_cidade.to_crs(CRS_PROJETADO)
    pontos_proj = subs_proj.copy()
    pontos_proj['geometry'] = subs_proj.geometry.centroid
    limite_proj = limite_cidade.to_crs(CRS_PROJETADO)

    print("Calculando polígonos de influência...")
    coords = np.array([(p.x, p.y) for p in pontos_proj.geometry])
    vor = Voronoi(coords)
    regions, vertices = voronoi_finite_polygons_2d(vor)
    
    polygons_list = []
    for region in regions:
        polygons_list.append(Polygon(vertices[region]))
    
    voronoi_gdf = gpd.GeoDataFrame(geometry=polygons_list, crs=CRS_PROJETADO)

    print("Ajustando fronteiras...")
    try:
        subs_logicas = gpd.overlay(voronoi_gdf, limite_proj, how='intersection')
    except:
        subs_logicas = gpd.clip(voronoi_gdf, limite_proj)

    subs_logicas_finais = gpd.sjoin(subs_logicas, pontos_proj, how="inner", predicate="contains")
    
    colunas_manter = ['geometry', 'NOM', 'COD_ID']
    cols = [c for c in colunas_manter if c in subs_logicas_finais.columns]
    subs_logicas_finais = subs_logicas_finais[cols]

    print("Salvando no banco de dados PostgreSQL...")
    try:
        salvar_voronoi(subs_logicas_finais.to_crs(epsg=4326))
        print("✅ Territórios Voronoi salvos no banco com sucesso!")
    except Exception as e:
        print(f"⚠️ Aviso: Não foi possível salvar no banco: {e}")

    print("Gerando mapa visual (PNG)...")
    try:
        import matplotlib.pyplot as plt
        
        fig, ax = plt.subplots(figsize=(12, 10))
        
        subs_logicas_finais.plot(ax=ax, alpha=0.5, edgecolor='black', cmap='tab20')
        
        nome_col = 'NOM' if 'NOM' in subs_logicas_finais.columns else 'NOME'
        if nome_col in subs_logicas_finais.columns:
            for idx, row in subs_logicas_finais.iterrows():
                centroid = row['geometry'].centroid
                ax.text(centroid.x, centroid.y, row[nome_col], 
                    fontsize=8, ha='center', bbox=dict(boxstyle='round', facecolor='white', alpha=0.7))
        
        ax.set_title(f'Territórios de Influência - {CIDADE_ALVO}')
        ax.axis('off')
        
        path_png = os.path.join(DIR_RAIZ, 'territorios_voronoi.png')
        plt.savefig(path_png, dpi=150, bbox_inches='tight')
        plt.close()
        
        print(f"✅ Mapa salvo em: {path_png}")
    except Exception as e:
        print(f"Aviso: Não foi possível gerar a imagem PNG: {e}")

if __name__ == "__main__":
    main()