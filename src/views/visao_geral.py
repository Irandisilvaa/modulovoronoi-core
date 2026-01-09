import streamlit as st
import pandas as pd
import folium
from streamlit_folium import st_folium
import os
import sys

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

def calcular_criticidade(potencia_gd_kw, consumo_anual_mwh):
    """
    Calcula o nível de criticidade baseado na injeção de potência na rede.
    
    Args:
        potencia_gd_kw: Potência instalada de GD em kW
        consumo_anual_mwh: Consumo anual em MWh
    
    Returns:
        tuple: (nivel_texto, cor_hex)
    """
    if consumo_anual_mwh == 0:
        return "NORMAL", "#28a745"
    
    geracao_estimada_mwh = (potencia_gd_kw * 4.5 * 365) / 1000
    percentual_injecao = (geracao_estimada_mwh / consumo_anual_mwh) * 100
    
    if percentual_injecao < 15:
        return "NORMAL", "#28a745"
    elif percentual_injecao < 30:
        return "MÉDIO", "#ffc107"
    else:
        return "CRÍTICO", "#dc3545"

def agregar_metricas_totais(df_mercado):
    """
    Agrega todas as métricas do sistema.
    
    Args:
        df_mercado: DataFrame com dados de mercado
    
    Returns:
        dict: Dicionário com métricas totais
    """
    total_subestacoes = len(df_mercado)
    total_clientes = 0
    total_paineis = 0
    total_potencia_kw = 0.0
    total_consumo_mwh = 0.0
    
    for _, row in df_mercado.iterrows():
        metricas = row.get('metricas_rede', {})
        if isinstance(metricas, str):
            import ast
            try:
                metricas = ast.literal_eval(metricas)
            except:
                metricas = {}
        
        total_clientes += metricas.get('total_clientes', 0)
        total_consumo_mwh += metricas.get('consumo_anual_mwh', 0)
        
        gd = row.get('geracao_distribuida', {})
        if isinstance(gd, str):
            import ast
            try:
                gd = ast.literal_eval(gd)
            except:
                gd = {}
        
        total_paineis += gd.get('total_unidades', 0)
        total_potencia_kw += gd.get('potencia_total_kw', 0)
    
    return {
        'total_subestacoes': total_subestacoes,
        'total_clientes': total_clientes,
        'total_paineis': total_paineis,
        'total_potencia_kw': total_potencia_kw,
        'total_consumo_mwh': total_consumo_mwh
    }

def criar_mapa_voronoi_semaforo(gdf, df_mercado):
    """
    Cria mapa Folium com polígonos de Voronoi coloridos por criticidade.
    
    Args:
        gdf: GeoDataFrame com geometrias das subestações
        df_mercado: DataFrame com dados de mercado
    
    Returns:
        folium.Map: Mapa configurado
    """
    centroid = gdf.to_crs(epsg=3857).geometry.centroid.to_crs(gdf.crs).unary_union.centroid
    
    m = folium.Map(
        location=[centroid.y, centroid.x],
        zoom_start=12,
        scrollWheelZoom=False,
        tiles='OpenStreetMap'
    )
    
    criticidade_map = {}
    for _, row in df_mercado.iterrows():
        id_tec = str(row.get('id_tecnico', ''))
        
        metricas = row.get('metricas_rede', {})
        gd = row.get('geracao_distribuida', {})
        
        if isinstance(metricas, str):
            import ast
            try:
                metricas = ast.literal_eval(metricas)
            except:
                metricas = {}
        
        if isinstance(gd, str):
            import ast
            try:
                gd = ast.literal_eval(gd)
            except:
                gd = {}
        
        potencia_kw = gd.get('potencia_total_kw', 0)
        consumo_mwh = metricas.get('consumo_anual_mwh', 0)
        
        nivel, cor = calcular_criticidade(potencia_kw, consumo_mwh)
        criticidade_map[id_tec] = {
            'nivel': nivel,
            'cor': cor,
            'nome': str(row.get('subestacao', '')).split(' (ID:')[0],
            'clientes': metricas.get('total_clientes', 0),
            'consumo': consumo_mwh,
            'potencia': potencia_kw,
            'paineis': gd.get('total_unidades', 0)
        }
    
    def style_function(feature):
        cod_id = str(feature['properties'].get('COD_ID', ''))
        info = criticidade_map.get(cod_id, {'cor': '#cccccc', 'nivel': 'DESCONHECIDO'})
        
        return {
            'fillColor': info['cor'],
            'color': 'white',
            'weight': 2,
            'fillOpacity': 0.6
        }
    
    def highlight_function(feature):
        return {
            'fillColor': '#ffff00',
            'color': 'white',
            'weight': 3,
            'fillOpacity': 0.8
        }
    
    for _, row in gdf.iterrows():
        cod_id = str(row.get('COD_ID', ''))
        info = criticidade_map.get(cod_id, {
            'nome': 'Desconhecido',
            'nivel': 'N/A',
            'clientes': 0,
            'consumo': 0,
            'potencia': 0,
            'paineis': 0
        })
        
        tooltip_html = f"""
        <div style="font-family: Arial; font-size: 12px;">
            <b>{info['nome']}</b><br>
            <b>Status:</b> {info['nivel']}<br>
            <b>Clientes:</b> {info['clientes']:,}<br>
            <b>Consumo:</b> {info['consumo']:.2f} MWh<br>
            <b>Potência GD:</b> {info['potencia']:.2f} kW<br>
            <b>Painéis:</b> {info['paineis']}
        </div>
        """
        
        folium.GeoJson(
            row.geometry,
            style_function=lambda x, cod=cod_id: style_function({'properties': {'COD_ID': cod}}),
            highlight_function=highlight_function,
            tooltip=folium.Tooltip(tooltip_html)
        ).add_to(m)
    
    return m

def render_view():
    """Renderiza a view de Panorama Geral."""
    st.title("⚡ Panorama Geral do Sistema")
    st.markdown("Visão geral de todas as subestações e indicadores agregados")
    
    try:
        from utils import carregar_dados_cache
    except ImportError as e:
        st.error(f"Erro ao importar utils: {e}")
        st.stop()
    
    with st.spinner("Carregando dados do sistema..."):
        gdf, dados_lista = carregar_dados_cache()
        
        if gdf is None or not dados_lista:
            st.error("❌ Falha ao carregar dados. Verifique se o ETL foi executado.")
            st.stop()
        
        df_mercado = pd.DataFrame(dados_lista)
    
    metricas = agregar_metricas_totais(df_mercado)
    
    st.header("📊 Indicadores Gerais")
    
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        st.metric(
            label="🏢 Subestações",
            value=f"{metricas['total_subestacoes']}"
        )
    
    with col2:
        st.metric(
            label="👥 Clientes",
            value=f"{metricas['total_clientes']:,}".replace(",", ".")
        )
    
    with col3:
        st.metric(
            label="☀️ Unidades MMGD",
            value=f"{metricas['total_paineis']:,}".replace(",", ".")
        )
    
    with col4:
        st.metric(
            label="⚡ Potência Instalada",
            value=f"{metricas['total_potencia_kw']:,.0f} kW".replace(",", ".")
        )
    
    st.divider()
    
    st.header("🗺️ Mapa de Criticidade das Subestações")
    
    st.markdown("""
    **Legenda de Criticidade:**
    - 🟢 **NORMAL**: Injeção < 15% do consumo
    - 🟡 **MÉDIO**: Injeção entre 15% e 30% do consumo
    - 🔴 **CRÍTICO**: Injeção > 30% do consumo (risco de inversão de fluxo)
    """)
    
    try:
        mapa = criar_mapa_voronoi_semaforo(gdf, df_mercado)
        st_folium(mapa, use_container_width=True, height=500)
    except Exception as e:
        st.error(f"Erro ao gerar mapa: {e}")
        import traceback
        st.code(traceback.format_exc())
    
    st.divider()
    
    st.header("📋 Resumo por Subestação")
    
    tabela_dados = []
    
    for _, row in df_mercado.iterrows():
        import ast
        
        nome = str(row.get('subestacao', '')).split(' (ID:')[0]
        id_tec = row.get('id_tecnico', '')
        
        metricas_row = row.get('metricas_rede', {})
        gd_row = row.get('geracao_distribuida', {})
        
        if isinstance(metricas_row, str):
            try:
                metricas_row = ast.literal_eval(metricas_row)
            except:
                metricas_row = {}
        
        if isinstance(gd_row, str):
            try:
                gd_row = ast.literal_eval(gd_row)
            except:
                gd_row = {}
        
        clientes = metricas_row.get('total_clientes', 0)
        consumo = metricas_row.get('consumo_anual_mwh', 0)
        potencia = gd_row.get('potencia_total_kw', 0)
        paineis = gd_row.get('total_unidades', 0)
        
        nivel, _ = calcular_criticidade(potencia, consumo)
        
        tabela_dados.append({
            'Subestação': nome,
            'ID': id_tec,
            'Clientes': clientes,
            'Consumo (MWh)': round(consumo, 2),
            'Potência GD (kW)': round(potencia, 2),
            'Painéis': paineis,
            'Status': nivel
        })
    
    df_tabela = pd.DataFrame(tabela_dados)
    
    ordem_criticidade = {'CRÍTICO': 0, 'MÉDIO': 1, 'NORMAL': 2}
    df_tabela['_ordem'] = df_tabela['Status'].map(ordem_criticidade)
    df_tabela = df_tabela.sort_values('_ordem').drop(columns=['_ordem'])
    
    def colorir_status(val):
        if val == 'CRÍTICO':
            return 'background-color: #dc3545; color: white'
        elif val == 'MÉDIO':
            return 'background-color: #ffc107; color: black'
        else:
            return 'background-color: #28a745; color: white'
    
    st.dataframe(
        df_tabela.style.applymap(colorir_status, subset=['Status']),
        use_container_width=True,
        hide_index=True
    )
    
    csv = df_tabela.to_csv(index=False, encoding='utf-8-sig')
    st.download_button(
        label="📥 Baixar Relatório Completo (CSV)",
        data=csv,
        file_name="panorama_geral_subestacoes.csv",
        mime="text/csv",
        use_container_width=False
    )
    
    st.divider()
    
    st.header("📈 Estatísticas do Sistema")
    
    col_stat1, col_stat2 = st.columns(2)
    
    with col_stat1:
        st.subheader("Distribuição de Criticidade")
        
        contagem_status = df_tabela['Status'].value_counts()
        
        import plotly.graph_objects as go
        
        cores_pizza = {
            'NORMAL': '#28a745',
            'MÉDIO': '#ffc107',
            'CRÍTICO': '#dc3545'
        }
        
        fig_pizza = go.Figure(data=[go.Pie(
            labels=contagem_status.index,
            values=contagem_status.values,
            marker=dict(colors=[cores_pizza.get(x, '#cccccc') for x in contagem_status.index]),
            hole=0.4
        )])
        
        fig_pizza.update_layout(
            height=300,
            margin=dict(t=20, b=20, l=20, r=20),
            showlegend=True
        )
        
        st.plotly_chart(fig_pizza, use_container_width=True)
    
    with col_stat2:
        st.subheader("Top 5 - Maior Potência GD")
        
        # 1. CRIA IDENTIFICADOR ÚNICO (Nome + ID)
        # Isso garante que subestações com mesmo nome não se sobreponham
        df_tabela['Identificacao_Unica'] = df_tabela['Subestação'] + " (ID: " + df_tabela['ID'].astype(str) + ")"
        
        # 2. Pega os Top 5 baseado na potência
        top5 = df_tabela.nlargest(5, 'Potência GD (kW)')
        
        # --- LÓGICA DE CORES ALEATÓRIAS/ESCALÁVEIS ---
        import plotly.express as px
        import random

        pool_cores = (
            px.colors.qualitative.Plotly + 
            px.colors.qualitative.Bold + 
            px.colors.qualitative.Vivid
        )
        
        qtde = len(top5)
        cores_finais = []
        
        if qtde <= len(pool_cores):
            cores_finais = pool_cores[:qtde]
        else:
            cores_finais = pool_cores[:]
            for _ in range(qtde - len(pool_cores)):
                cores_finais.append("#{:06x}".format(random.randint(0, 0xFFFFFF)))
        # ---------------------------------------------

        fig_barras = go.Figure(data=[go.Bar(
            x=top5['Identificacao_Unica'],  # <--- USA O ID COMPOSTO NO EIXO X
            y=top5['Potência GD (kW)'],
            marker_color=cores_finais,
            # Texto formatado padrão BR
            text=top5['Potência GD (kW)'].apply(lambda x: f"{x:,.0f} kW".replace(",", "X").replace(".", ",").replace("X", ".")),
            textposition='auto',
            # No hover, mostra o nome limpo e o ID separado
            hovertemplate='<b>%{x}</b><br>Potência: %{y:,.2f} kW<extra></extra>'
        )])
        
        fig_barras.update_layout(
            height=300,
            margin=dict(t=20, b=40, l=20, r=20), # Aumentei margem inferior para caber os nomes longos
            xaxis_title="",
            yaxis_title="Potência (kW)",
            showlegend=False,
            # Se os nomes ficarem muito grandes, rotaciona um pouco
            xaxis=dict(tickangle=-15) 
        )
        
        st.plotly_chart(fig_barras, use_container_width=True)
    
    penetracao_media = (metricas['total_potencia_kw'] * 4.5 * 365 / 1000) / metricas['total_consumo_mwh'] * 100 if metricas['total_consumo_mwh'] > 0 else 0
    
    st.info(f"""
    **📊 Análise Geral do Sistema:**
    - Penetração média de GD: **{penetracao_media:.1f}%**
    - Consumo total anual: **{metricas['total_consumo_mwh']:,.2f} MWh**
    - Capacidade de geração instalada: **{metricas['total_potencia_kw']:,.2f} kW**
    """.replace(",", "."))
    
    st.caption(f"GridScope v5.0 Enterprise | Dashboard ")
