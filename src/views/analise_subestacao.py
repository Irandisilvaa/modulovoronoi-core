import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import folium
from streamlit_folium import st_folium
import os
import sys
import ast
from datetime import date
import warnings

try:
    sys.path.append(os.path.dirname(os.path.abspath(__file__)))
    import tab_ia
except ImportError:
    tab_ia = None 

def render_view():
    warnings.filterwarnings("ignore", category=UserWarning)
    warnings.filterwarnings("ignore", message=".*use_container_width.*")

    sys.path.append(os.path.dirname(os.path.abspath(__file__)))
    parent_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if parent_dir not in sys.path:
        sys.path.append(parent_dir)

    try:
        from utils import carregar_dados_cache, limpar_float
    except ImportError as e:
        st.error(f"Erro de importação: {e}. Verifique se 'utils.py' existe na raiz.")
        st.stop()

    CATEGORIAS_ALVO = ["Residencial", "Comercial", "Industrial", "Rural", "Poder Público"]

    CORES_MAPA = {
        "Residencial": "#007bff",        
        "Comercial": "#ffc107",          
        "Industrial": "#dc3545",         
        "Rural": "#28a745",              
        "Poder Público": "#6f42c1",      
    }

    def formatar_br(valor):
        """Formata números para o padrão brasileiro."""
        if isinstance(valor, str): return valor
        try:
            return f"{float(valor):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
        except (ValueError, TypeError):
            return str(valor)

    def converter_para_dict(dado):
        """Converte string para dicionário se necessário."""
        if isinstance(dado, dict):
            return dado
        if isinstance(dado, str):
            try:
                return ast.literal_eval(dado)
            except (ValueError, SyntaxError):
                return {}
        return {}

    @st.cache_data
    def obter_dados_dashboard():
        """Carrega dados geoespaciais e de mercado (cacheado)."""
        try:
            gdf, dados_lista = carregar_dados_cache()
            if gdf is None or not dados_lista:
                return None, None
            return gdf, pd.DataFrame(dados_lista)
        except Exception as e:
            st.error(f"Erro ao processar dados de cache: {e}")
            return None, None
        
    gdf, df_mercado = obter_dados_dashboard()

    if gdf is None or df_mercado is None:
        st.error("❌ Falha crítica: Dados não carregados. Verifique se o ETL rodou.")
        st.stop()

    mapa_opcoes = {}
    if 'subestacao' in df_mercado.columns:
        for idx, row in df_mercado.iterrows():
            id_tec = row.get('id_tecnico', idx)
            label = row['subestacao']
            mapa_opcoes[label] = id_tec

    if not mapa_opcoes:
        st.warning("Nenhuma subestação disponível nos dados de mercado.")
        st.stop()

    escolha_label = st.sidebar.selectbox("Selecione a Subestação:", sorted(mapa_opcoes.keys()))
    id_escolhido = mapa_opcoes[escolha_label]

    data_analise = st.sidebar.date_input("Data da Análise:", date.today())
    modo = "Auditoria (Histórico)" if data_analise < date.today() else "Operação (Tempo Real/Prev)"
    st.sidebar.info(f"Modo Atual: {modo}")

    area_sel = gdf[gdf["COD_ID"].astype(str) == str(id_escolhido)]

    centroid_existe = False
    lat_c, lon_c = -10.9472, -37.0731 

    if not area_sel.empty:
        centroid_existe = True
        try:
            c = area_sel.geometry.centroid.iloc[0]
            lat_c, lon_c = c.y, c.x
        except Exception:
            pass

    try:
        if 'id_tecnico' in df_mercado.columns:
            dados_filtrados = df_mercado[df_mercado["id_tecnico"].astype(str) == str(id_escolhido)]
        else:
            dados_filtrados = df_mercado[df_mercado["subestacao"] == escolha_label]

        if dados_filtrados.empty:
            dados_filtrados = df_mercado.iloc[[0]]

        dados_raw = dados_filtrados.iloc[0]
        nome_limpo_escolha = str(dados_raw["subestacao"]).split(' (ID:')[0]
        subestacao_obj = {
            "id": str(id_escolhido),
            "nome": nome_limpo_escolha
        }

    except Exception as e:
        st.error(f"Erro ao recuperar dados da tabela: {e}")
        st.stop()

    metricas = converter_para_dict(dados_raw.get("metricas_rede", {}))
    dados_gd = converter_para_dict(dados_raw.get("geracao_distribuida", {}))
    perfil = converter_para_dict(dados_raw.get("perfil_consumo", {}))

    st.title(f"Monitoramento: {subestacao_obj['nome']}")
    st.caption(f"ID Técnico: {id_escolhido}")
    st.markdown(f"**Localização:** Aracaju - SE | **Status:** Conectado")

    st.header("Infraestrutura de Rede")
    k1, k2, k3, k4 = st.columns(4)
    with k1:
        st.metric("Total de Clientes", f"{metricas.get('total_clientes', 0):,}".replace(",", "."))
    with k2:
        st.metric("Consumo Anual (MWh)", f"{formatar_br(metricas.get('consumo_anual_mwh', 0))} ")
    with k3:
        st.metric("Unidades MMGD", f"{dados_gd.get('total_unidades', 0)}")
    with k4:
        st.metric("Potência Solar Instalada (kW)", f"{formatar_br(dados_gd.get('potencia_total_kw', 0))}")

    st.divider()

    tab_visao_geral, tab_ia_render = st.tabs(["📊 Visão Geral & Perfil", "🧠 Inteligência Artificial & Simulação"])

    with tab_visao_geral:
        st.subheader("Potência da GD Instalada por Classe")

        detalhe_raw = converter_para_dict(dados_gd.get("detalhe_por_classe", {}))
        detalhe_gd = {k: v for k, v in detalhe_raw.items() if k in CATEGORIAS_ALVO and v > 0}

        if detalhe_gd:
            detalhe_gd = dict(sorted(detalhe_gd.items(), key=lambda item: item[1], reverse=True))
            lista_cores = [CORES_MAPA.get(k, '#1f77b4') for k in detalhe_gd.keys()]

            fig_barras = go.Figure(data=[go.Bar(
                x=list(detalhe_gd.keys()),
                y=list(detalhe_gd.values()),
                marker_color='#1f77b4',
                text=[f"{v:,.1f} kW".replace(",", "X").replace(".", ",").replace("X", ".") for v in
                    detalhe_gd.values()],
                textposition='auto'
            )])
            
            fig_barras.update_layout(height=250, margin=dict(l=10, r=10, t=10, b=10), yaxis_title="kW")
            st.plotly_chart(fig_barras, use_container_width=True)
        else:
            st.info("Sem dados de GD para as categorias selecionadas.")

        st.divider()

        st.subheader("📍 Área de Cobertura Geográfica")
        if centroid_existe:
            m = folium.Map(location=[lat_c, lon_c], zoom_start=13, scrollWheelZoom=False)

            def style_fn(feature):
                feature_id = feature['properties'].get('COD_ID')
                is_sel = (str(feature_id) == str(id_escolhido))
                cor = '#007bff' if is_sel else 'gray'
                return {'fillColor': cor, 'color': 'white' if is_sel else 'gray', 'weight': 3 if is_sel else 1,
                        'fillOpacity': 0.7 if is_sel else 0.3}

            folium.GeoJson(gdf, style_function=style_fn, tooltip=folium.GeoJsonTooltip(fields=["NOM", "COD_ID"],
                                                                                    aliases=["Subestação:",
                                                                                            "ID:"])).add_to(m)
            st_folium(m, use_container_width=True, height=400)
        else:
            st.warning("⚠️ Geometria não encontrada para este ID.")

        st.divider()

        st.subheader("📌 Segmentação de Mercado")

        col_graf1, col_graf2 = st.columns(2)

        with col_graf1:
            st.markdown("**Distribuição de Clientes (Qtd)**")
            dados_clientes = []
            for k, v in perfil.items():
                if k in CATEGORIAS_ALVO:
                    v_dict = converter_para_dict(v)
                    val = v_dict.get("qtd_clientes", 0)
                    if val > 0:
                        dados_clientes.append({"Segmento": k, "Valor": val})

            df_pie = pd.DataFrame(dados_clientes)
            if not df_pie.empty:
                fig_pie = px.pie(df_pie, values="Valor", names="Segmento", hole=0.4, color="Segmento",
                                color_discrete_map=CORES_MAPA)
                fig_pie.update_layout(
                    margin=dict(t=20, b=20, l=20, r=20),
                    height=350,
                    showlegend=True,
                    legend=dict(orientation="h", y=-0.1)
                )
                fig_pie.update_traces(
                    textposition='auto',
                    textinfo='percent+label',
                    textfont_size=13,
                    hovertemplate='%{label}<br>Qtd: %{value}<br>%{percent}'
                )
                st.plotly_chart(fig_pie, use_container_width=True)
            else:
                st.info("Sem dados de Clientes.")

        with col_graf2:
            st.markdown("**Carga por Classe (Consumo MWh)**")
            dados_carga = []
            if perfil:
                for k, v in perfil.items():
                    if k not in CATEGORIAS_ALVO: continue
                    v_dict = converter_para_dict(v)
                    val_candidato = (v_dict.get("consumo_anual_mwh") or v_dict.get("ENE_12") or 0)
                    val_float = limpar_float(val_candidato)
                    if val_float > 0:
                        dados_carga.append({"Segmento": k, "Valor": val_float})
            
            df_carga = pd.DataFrame(dados_carga)
            if not df_carga.empty:
                df_carga = df_carga.sort_values(by="Valor", ascending=False)

                fig_carga = go.Figure(data=[
                    go.Bar(
                        x=df_carga["Segmento"],
                        y=df_carga["Valor"],
                        marker_color=[CORES_MAPA.get(s, '#17a2b8') for s in df_carga["Segmento"]],
                        text=[f"{val:,.0f} MWh".replace(",", "X").replace(".", ",").replace("X", ".") for val in
                            df_carga["Valor"]],
                        textposition='auto',
                        hovertemplate='<b>%{x}</b><br>Consumo: %{y:,.2f} MWh<extra></extra>'
                    )
                ])
                fig_carga.update_layout(
                    margin=dict(t=20, b=20, l=20, r=20),
                    height=350,
                    yaxis_title="Consumo Anual (MWh)",
                    showlegend=False,
                    xaxis=dict(title=None)
                )
                st.plotly_chart(fig_carga, use_container_width=True)
            else:
                st.info("Sem dados de Carga.")

        st.divider()

        st.header("📋 Relatório Técnico & Ações")
        col_table, col_actions = st.columns([2, 1])

        with col_table:
            st.subheader("Dados Consolidados")
            dados_consolidados = {
                "Parâmetro": ["Subestação", "ID", "Consumo Anual", "Potência GD", "Clientes"],
                "Valor": [
                    subestacao_obj['nome'], 
                    str(id_escolhido),
                    f"{formatar_br(metricas.get('consumo_anual_mwh', 0))} MWh",
                    f"{formatar_br(dados_gd.get('potencia_total_kw', 0))} kW",
                    str(metricas.get('total_clientes', 0))
                ]
            }
            st.dataframe(pd.DataFrame(dados_consolidados), use_container_width=True, hide_index=True)

        with col_actions:
            st.subheader("Diagnóstico")
            potencia_kw = limpar_float(dados_gd.get('potencia_total_kw', 0))
            consumo_mwh = limpar_float(metricas.get('consumo_anual_mwh', 1))
            if consumo_mwh == 0: consumo_mwh = 1
            
            geracao_est_mwh = (potencia_kw * 4.5 * 365) / 1000
            penetracao = (geracao_est_mwh / consumo_mwh) * 100
            
            st.write(f"**Penetração GD:** {penetracao:.1f}%")
            if penetracao > 25:
                st.warning("⚠️ Risco de inversão de fluxo.")
            else:
                st.success("✅ **Rede Estável:** Capacidade disponível.")

            csv = pd.DataFrame(dados_consolidados).to_csv(index=False).encode('utf-8')
            st.download_button(label="📥 Baixar Relatório CSV", data=csv, file_name=f"relatorio_{id_escolhido}.csv",
                            mime="text/csv", use_container_width=True)

    with tab_ia_render:
        tab_ia.render_tab_ia(subestacao_obj, data_analise, dados_gd)

    st.caption(f"GridScope v4.9 Enterprise | Dados atualizados em: {date.today().strftime('%d/%m/%Y')}")