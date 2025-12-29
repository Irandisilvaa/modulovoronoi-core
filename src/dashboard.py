import streamlit as st
import geopandas as gpd
import pandas as pd
import json
import plotly.express as px
import folium
from streamlit_folium import st_folium
import os

st.set_page_config(layout="wide", page_title="GridScope - Aracaju", page_icon="⚡")

# --- CARREGAR DADOS ---
@st.cache_data
def carregar_dados():
    # Lógica para encontrar arquivos
    if os.path.exists("subestacoes_logicas_aracaju.geojson"):
        caminho_geo = "subestacoes_logicas_aracaju.geojson"
        caminho_json = "perfil_mercado_aracaju.json"
    else:
        caminho_geo = "../subestacoes_logicas_aracaju.geojson"
        caminho_json = "../perfil_mercado_aracaju.json"

    gdf = gpd.read_file(caminho_geo)
    
    # Cria o centroide para os pinos (mas vamos remover antes de desenhar as áreas)
    gdf['centroide'] = gdf.geometry.centroid
    
    with open(caminho_json, 'r', encoding='utf-8') as f:
        dados_mercado = json.load(f)
    
    return gdf, pd.DataFrame(dados_mercado)

try:
    gdf, df_mercado = carregar_dados()
except:
    st.error("Arquivos não encontrados. Rode 'src/analise_mercado.py' primeiro!")
    st.stop()

# --- SIDEBAR ---
st.sidebar.title("⚡ GridScope")
st.sidebar.markdown("**Inteligência de Mercado**")

lista_subs = sorted(gdf['NOM'].unique())
escolha = st.sidebar.selectbox("Selecione a Subestação:", lista_subs)

# Filtrar dados
area_sel = gdf[gdf['NOM'] == escolha]
dados_sel = df_mercado[df_mercado['subestacao'] == escolha].iloc[0]

# --- DASHBOARD ---
st.title(f"📍 Subestação: {escolha}")

# Métricas
col1, col2, col3 = st.columns(3)
col1.metric("🏠 Clientes Totais", f"{dados_sel['total_clientes_estimados']:,}".replace(",", "."))
col2.metric("⚡ Consumo Mensal", f"{dados_sel['consumo_total_kwh_mes']/1000:,.0f} MWh")
col3.metric("🗺️ Área de Atuação", f"{area_sel.to_crs(31984).area.sum()/1e6:.2f} km²")

st.divider()

col_graf, col_map = st.columns([1, 2])

with col_graf:
    st.subheader("Perfil de Consumo")
    perfil = dados_sel['perfil']
    
    df_pizza = pd.DataFrame([
        {"Segmento": k, "Clientes": v["qtd"]} 
        for k,v in perfil.items() if v["qtd"] > 0
    ])
    
    cores = {
        'Residencial': '#007bff', 
        'Comercial': '#ffc107',   
        'Industrial': '#dc3545'   
    }
    
    if not df_pizza.empty:
        fig = px.pie(df_pizza, values='Clientes', names='Segmento', hole=0.4, 
                     color='Segmento', color_discrete_map=cores)
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("Sem dados de perfil para esta subestação.")

    qtd_ind = perfil.get('Industrial', {}).get('qtd', 0)
    if qtd_ind > 0:
        st.error(f"🏭 **Zona Industrial:** {qtd_ind} grandes clientes.")
    else:
        st.success("🏡 **Zona Residencial/Comercial**")

with col_map:
    st.subheader("Visualização Geográfica")
    
    centro_lat = area_sel.geometry.centroid.y.values[0]
    centro_lon = area_sel.geometry.centroid.x.values[0]
    
    # --- MUDANÇA AQUI: tiles="OpenStreetMap" para cores vivas ---
    m = folium.Map(location=[centro_lat, centro_lon], zoom_start=13, tiles="OpenStreetMap")
    
    # 1. Áreas de Fundo (Todas as outras subestações)
    # Deixei o contorno (color) preto e fino, e o preenchimento (fillColor) azul bem clarinho e transparente
    folium.GeoJson(
        gdf.drop(columns=['centroide'], errors='ignore'), 
        style_function=lambda x: {
            'fillColor': '#3388ff', 
            'color': 'black',       # Contorno preto para definir bem o bairro
            'weight': 1, 
            'fillOpacity': 0.1      # Bem transparente para ver o mapa embaixo
        },
        tooltip=folium.GeoJsonTooltip(fields=['NOM'], aliases=['Subestação:'])
    ).add_to(m)
    
    # 2. Área Selecionada (Destaque)
    # Laranja forte, mas com opacidade 0.4 para ler os nomes das ruas
    folium.GeoJson(
        area_sel.drop(columns=['centroide'], errors='ignore'),
        style_function=lambda x: {
            'fillColor': '#e67e22', # Laranja Energisa
            'color': '#d35400',     # Contorno Laranja Escuro
            'weight': 3,            # Contorno mais grosso
            'fillOpacity': 0.4      # Transparência média
        }
    ).add_to(m)

    # 3. Marcadores (Pinos)
    folium.Marker(
        [centro_lat, centro_lon],
        popup=f"<b>{escolha}</b>",
        icon=folium.Icon(color='red', icon='bolt', prefix='fa')
    ).add_to(m)
    
    for _, row in gdf.iterrows():
        if row['NOM'] != escolha:
            folium.CircleMarker(
                location=[row.centroide.y, row.centroide.x],
                radius=4,               # Bolinha um pouco maior
                color='#333',           # Borda escura
                weight=1,
                fill=True,
                fill_color='white',     # Miolo branco para destacar no mapa colorido
                fill_opacity=1,
                popup=row['NOM']
            ).add_to(m)

    st_folium(m, use_container_width=True, height=500)