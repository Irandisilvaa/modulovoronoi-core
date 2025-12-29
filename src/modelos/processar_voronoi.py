import geopandas as gpd
import matplotlib.pyplot as plt
import osmnx as ox
import numpy as np
import os
import sys
from scipy.spatial import Voronoi
from shapely.geometry import Polygon
from shapely.ops import unary_union

# --- CORREÇÃO DE IMPORTAÇÃO (FIX) ---
# Adiciona a pasta pai 'src' ao caminho do Python
# Isso permite que 'src/modelos' enxergue 'src/etl'
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

try:
    # Tenta importar da nova estrutura organizada (Opção A)
    from etl import carregador_aneel as etl_bdgd
    print("Módulo de ETL carregado com sucesso.")
except ImportError:
        print("ERRO CRÍTICO: Não foi possível importar o carregador de dados.")
        print("Verifique se 'src/etl/carregador_aneel.py' existe.")
        sys.exit(1)
# --- FIM DA CORREÇÃO ---

# --- CONFIGURAÇÕES ---
CIDADE_ALVO = "Aracaju, Sergipe, Brazil"
CRS_PROJETADO = "EPSG:31984" # SIRGAS 2000 / UTM zone 24S (Metros)

def voronoi_finite_polygons_2d(vor, radius=None):
    """
    Reconstrói regiões de Voronoi finitas para uso em mapas geográficos.
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
            
            t = vor.points[p2] - vor.points[p1] # tangent
            t /= np.linalg.norm(t)
            n = np.array([-t[1], t[0]])  # normal
            
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
    print(f"INICIANDO PROCESSAMENTO PARA: {CIDADE_ALVO}")
    
    # 1. CARREGAR DADOS (Via ETL)
    subs_raw = etl_bdgd.carregar_subestacoes()
    
    # 2. CARREGAR LIMITES TERRITORIAIS (OSM)
    print(f"Baixando limites de {CIDADE_ALVO} via OpenStreetMap...")
    try:
        limite_cidade = ox.geocode_to_gdf(CIDADE_ALVO)
    except Exception as e:
        print(f"Erro ao baixar dados do OSM: {e}")
        return

    # 3. UNIFORMIZAR PROJEÇÕES (CRÍTICO)
    # Garante que tudo esteja no mesmo sistema antes de recortar
    if subs_raw.crs is None:
        subs_raw.set_crs(epsg=4674, inplace=True) # SIRGAS 2000 Lat/Long
    
    limite_cidade = limite_cidade.to_crs(subs_raw.crs)

    # 4. RECORTAR (CLIP)
    print("Filtrando apenas subestações dentro do município...")
    subs_cidade = gpd.clip(subs_raw, limite_cidade)
    print(f"   -> Subestações encontradas na área urbana: {len(subs_cidade)}")
    
    if len(subs_cidade) < 2:
        print("AVISO: Menos de 2 subestações encontradas. Impossível gerar Voronoi.")
        return

    # 5. CONVERTER PARA METROS (PROJEÇÃO PLANA)
    subs_proj = subs_cidade.to_crs(CRS_PROJETADO)
    pontos_proj = subs_proj.copy()
    
    # Garante que usamos o centróide (caso venha polígono da ANEEL)
    pontos_proj['geometry'] = subs_proj.geometry.centroid
    limite_proj = limite_cidade.to_crs(CRS_PROJETADO)

    # 6. CÁLCULO VORONOI
    print("Calculando diagrama matemático de Voronoi...")
    coords = np.array([(p.x, p.y) for p in pontos_proj.geometry])
    vor = Voronoi(coords)
    regions, vertices = voronoi_finite_polygons_2d(vor)
    
    polygons_list = []
    for region in regions:
        polygons_list.append(Polygon(vertices[region]))
    
    voronoi_gdf = gpd.GeoDataFrame(geometry=polygons_list, crs=CRS_PROJETADO)

    # 7. INTERSEÇÃO COM LIMITE DA CIDADE
    print("Recortando polígonos infinitos no formato da cidade...")
    try:
        # Overlay intersection é mais seguro que clip para geometrias complexas geradas
        subs_logicas = gpd.overlay(voronoi_gdf, limite_proj, how='intersection')
    except:
        # Fallback se der erro de topologia
        subs_logicas = gpd.clip(voronoi_gdf, limite_proj)

    # 8. SPATIAL JOIN (Recuperar Nomes)
    # O Voronoi perde os atributos originais, precisamos pegar de volta baseando-se na posição
    print("Associando nomes das subestações às áreas...")
    subs_logicas_finais = gpd.sjoin(subs_logicas, pontos_proj, how="inner", predicate="contains")
    
    # Limpeza de colunas duplicadas pelo join
    colunas_manter = ['geometry', 'NOM', 'COD_ID']
    # Filtra só o que existe
    cols = [c for c in colunas_manter if c in subs_logicas_finais.columns]
    subs_logicas_finais = subs_logicas_finais[cols]

    # 9. SALVAR ARQUIVO FINAL
    # Salva na raiz do projeto (voltando uma pasta de src/modelos)
    arquivo_saida = "subestacoes_logicas_aracaju.geojson"
    caminho_saida = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", arquivo_saida)
    
    # Converte de volta para Lat/Long (Padrão Web/GeoJSON)
    subs_logicas_finais.to_crs(epsg=4326).to_file(caminho_saida, driver='GeoJSON')
    print(f"SUCESSO! GeoJSON gerado em: {os.path.abspath(caminho_saida)}")

    # 10. PLOTAR (PREVIEW)
    print("Gerando imagem de visualização...")
    fig, ax = plt.subplots(figsize=(10, 10))
    
    # Desenha limite da cidade
    limite_proj.plot(ax=ax, color='#f4f4f4', edgecolor='#999999', linewidth=1)
    
    # Desenha Voronoi colorido
    subs_logicas_finais.plot(ax=ax, column='NOM', cmap='tab20', alpha=0.6, edgecolor='white', linewidth=0.5)
    
    # Desenha os Pontos Reais
    pontos_proj.plot(ax=ax, color='#333333', markersize=15, zorder=5)
    
    # Adiciona Rótulos
    for x, y, label in zip(pontos_proj.geometry.x, pontos_proj.geometry.y, pontos_proj['NOM']):
        ax.text(x, y, str(label), fontsize=7, ha='center', va='bottom', fontweight='bold', color='#222222')

    plt.title(f"GridScope: Áreas de Atuação - {CIDADE_ALVO}", fontsize=14)
    plt.axis('off')
    plt.tight_layout()
    plt.show()

if __name__ == "__main__":
    main()