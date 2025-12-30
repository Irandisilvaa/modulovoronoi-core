import streamlit as st
import pandas as pd
import plotly.express as px
import folium
from streamlit_folium import st_folium
import os
import sys
import requests
from datetime import date

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from utils import carregar_dados_cache

st.set_page_config(layout="wide", page_title="GridScope")

CATEGORIAS_ALVO = ['Residencial', 'Comercial', 'Industrial']
CORES_MAPA = {
    'Residencial': '#007bff', 
    'Comercial': '#ffc107', 
    'Industrial': '#dc3545'
}

@st.cache_data
def obter_dados_dashboard():
    """
    Wrapper para carregar dados usando a função centralizada do utils.py
    Transforma a lista de dicionários em DataFrame para facilitar o uso no Dashboard.
    """
    try:
        gdf, dados_lista = carregar_dados_cache()
        return gdf, pd.DataFrame(dados_lista)
    except Exception as e:
        raise Exception(f"Erro ao carregar dados base: {e}")

def consultar_simulacao(subestacao, data_escolhida):
    """
    Consulta a API local para simulação em tempo real.
    """
    data_str = data_escolhida.strftime("%d-%m-%Y")
    url = f"http://127.0.0.1:8000/simulacao/{subestacao}?data={data_str}"
    try:
        response = requests.get(url, timeout=5)
        if response.status_code == 200:
            return response.json()
    except:
        return None
    return None

try:
    gdf, df_mercado = obter_dados_dashboard()
except Exception as e:
    st.error(f"Erro Crítico: {e}")
    st.stop()

st.sidebar.title("GridScope")
st.sidebar.caption("Centro de Operacoes Integrado")

lista_subs = sorted(gdf['NOM'].unique())
escolha = st.sidebar.selectbox("Selecione a Subestacao:", lista_subs)

data_analise = st.sidebar.date_input("Data da Analise:", date.today(), format="DD/MM/YYYY")

modo = "Auditoria (Passado)" if data_analise < date.today() else "Previsao (Futuro)"
st.sidebar.info(f"Modo: {modo}")

area_sel = gdf[gdf['NOM'] == escolha]
dados_raw = df_mercado[df_mercado['subestacao'] == escolha].iloc[0]

metricas = dados_raw.get('metricas_rede', {})
dados_gd = dados_raw.get('geracao_distribuida', {})
perfil = dados_raw.get('perfil_consumo', {})
detalhe_gd = dados_gd.get('detalhe_por_classe', {})

st.title(f"Subestacao: {escolha}")

st.header("Infraestrutura Instalada")
c1, c2, c3, c4 = st.columns(4)
c1.metric("Clientes", f"{metricas.get('total_clientes', 0):,}".replace(",", "."))
c2.metric("Carga Anual (MWh)", f"{metricas.get('consumo_anual_mwh', 0):,.0f}")
c3.metric("Usinas Solares", dados_gd.get('total_unidades', 0))
c4.metric("Potencia Instalada (kW)", f"{dados_gd.get('potencia_total_kw', 0):,.0f}")

st.divider()
st.header(f"Simulacao VPP: {data_analise.strftime('%d/%m/%Y')}")

dados_simulacao = consultar_simulacao(escolha, data_analise)

if dados_simulacao:
    sc1, sc2, sc3, sc4 = st.columns(4)
    
    sc1.metric("Condicao do Tempo", dados_simulacao['condicao_tempo'])
    sc2.metric("Irradiacao (kWh/m2)", dados_simulacao['irradiacao_solar_kwh_m2'])
    sc3.metric("Temperatura Max (C)", dados_simulacao['temperatura_max_c'])
    
    perda = dados_simulacao['fator_perda_termica']
    sc4.metric("Perda Termica", f"-{perda}%")
    
    res1, res2 = st.columns([1, 2])
    
    geracao = dados_simulacao.get('geracao_estimada_mwh', 0)
    
    delta_cor = "normal"
    if geracao > 100: delta_cor = "inverse"
    
    res1.metric("Geracao Estimada (MWh)", f"{geracao}", delta_color=delta_cor)
    
    msg_impacto = dados_simulacao['impacto_na_rede']
    
    if "ALTA" in msg_impacto or "CRITICO" in msg_impacto:
        st.error(msg_impacto)
    elif "BAIXA" in msg_impacto:
        st.warning(msg_impacto)
    else:
        st.success(msg_impacto)
else:
    st.warning("⚠️ API de Simulação Offline. Inicie o servidor (api.py) para ver previsões em tempo real.")

st.divider()
col_graf, col_map = st.columns([1.5, 2])

with col_graf:
    st.subheader("Perfil de Consumo")
    dados_pie = [{"Segmento": k, "Clientes": v["qtd_clientes"]} for k,v in perfil.items() if k in CATEGORIAS_ALVO]
    df_cons = pd.DataFrame(dados_pie)
    
    if not df_cons.empty:
        fig_cons = px.pie(df_cons, values='Clientes', names='Segmento', hole=0.4, 
                          color='Segmento', color_discrete_map=CORES_MAPA)
        fig_cons.update_layout(height=250, margin=dict(t=0, b=0, l=0, r=0))
        st.plotly_chart(fig_cons, use_container_width=True)
    
    st.subheader("Potencia por Classe (kW)")
    if detalhe_gd:
        dados_bar = [{"Segmento": k, "Potencia_kW": v} for k,v in detalhe_gd.items() if k in CATEGORIAS_ALVO and v > 0]
        df_gd_class = pd.DataFrame(dados_bar)
        
        if not df_gd_class.empty:
            fig_gd = px.bar(df_gd_class, x='Segmento', y='Potencia_kW', color='Segmento', 
                            text_auto='.2s', color_discrete_map=CORES_MAPA)
            fig_gd.update_layout(height=300, showlegend=False)
            st.plotly_chart(fig_gd, use_container_width=True)
        else:
            st.info("Sem GD significativa nessas categorias.")

with col_map:
    st.subheader("Mapa da Area")
    if not area_sel.empty:
        centro_lat = area_sel.geometry.centroid.y.values[0]
        centro_lon = area_sel.geometry.centroid.x.values[0]
        m = folium.Map(location=[centro_lat, centro_lon], zoom_start=13, tiles="OpenStreetMap")
        
        def style_function(feature):
            nome = feature['properties']['NOM']
            dado = df_mercado[df_mercado['subestacao'] == nome]
            risco = 'BAIXO'
            if not dado.empty:
                metricas_dict = dado.iloc[0].get('metricas_rede', {})
                risco = metricas_dict.get('nivel_criticidade_gd', 'BAIXO')
            
            cor = {'BAIXO': '#2ecc71', 'MEDIO': '#f1c40f', 'ALTO': '#e74c3c'}.get(risco, '#2ecc71')
            
            opac = 0.6 if nome == escolha else 0.2
            weight = 3 if nome == escolha else 1
            return {'fillColor': cor, 'color': 'black', 'weight': weight, 'fillOpacity': opac}

        folium.GeoJson(
            gdf, 
            style_function=style_function, 
            tooltip=folium.GeoJsonTooltip(fields=['NOM'], aliases=['Subestação:'])
        ).add_to(m)
        
        st_folium(m, use_container_width=True, height=600)