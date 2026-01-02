import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import folium
from streamlit_folium import st_folium
import requests
import os
import sys
from datetime import date, timedelta

# Garante que o Python encontre os módulos da pasta raiz
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

try:
    from utils import carregar_dados_cache
    from etl.etl_ai_consumo import buscar_dados_reais_para_ia 
except ImportError as e:
    st.error(f"Erro de importação: {e}. Verifique se 'utils.py' e 'etl/etl_ai_consumo.py' existem.")
    st.stop()

st.set_page_config(
    layout="wide", 
    page_title="GridScope | Intelligence Dashboard",
    page_icon="⚡"
)

CATEGORIAS_ALVO = ["Residencial", "Comercial", "Industrial"]
CORES_MAPA = {
    "Residencial": "#007bff",
    "Comercial": "#ffc107",
    "Industrial": "#dc3545",
}

def formatar_br(valor):
    """Formata números para o padrão brasileiro."""
    return f"{valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

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

def consultar_simulacao(subestacao, data_escolhida):
    """Consulta API de Simulação Solar (Backend 8000)."""
    data_str = data_escolhida.strftime("%d-%m-%Y")
    url = f"http://127.0.0.1:8000/simulacao/{subestacao}?data={data_str}"
    try:
        response = requests.get(url, timeout=5)
        if response.status_code == 200:
            return response.json()
    except:
        return None
    return None

def consultar_ia_predict(payload):
    """Consulta crua à API de Inteligência Artificial (Backend 8001)."""
    try:
        resp = requests.post(
            "http://127.0.0.1:8001/predict/duck-curve",
            json=payload,
            timeout=10
        )
        if resp.status_code == 200:
            return resp.json(), None
        elif resp.status_code == 422:
            return None, f"Erro 422: Dados inválidos enviados. Verifique o Payload."
        else:
            return None, f"Erro na API: {resp.status_code}"
    except requests.exceptions.ConnectionError:
        return None, "Serviço de IA Offline (Porta 8001)"
    except Exception as e:
        return None, str(e)

@st.cache_data(ttl=600, show_spinner=False)
def obter_previsao_ia_cached(subestacao, data_str, potencia_gd, lat, lon):
    """
    Realiza o ETL e a consulta à IA.
    """
    # 1. Busca dados reais do histórico (ETL)
    dados_reais = buscar_dados_reais_para_ia(subestacao)
    
    consumo_anual = 0.0
    if dados_reais and "erro" not in dados_reais:
        consumo_anual = dados_reais.get('consumo_anual_mwh', 0)
    else:
        consumo_anual = 6000.0 # Fallback seguro se não achar no banco
    
    # 2. Converte Anual para Média Mensal
    consumo_mes_estimado = consumo_anual / 12

    # 3. Monta Payload
    payload = {
        "data_alvo": data_str,
        "potencia_gd_kw": float(potencia_gd),
        "consumo_mes_alvo_mwh": float(consumo_mes_estimado),
        "lat": float(lat),
        "lon": float(lon)
    }

    # 4. Chama a API
    return consultar_ia_predict(payload)

# --- CARREGAMENTO INICIAL ---
gdf, df_mercado = obter_dados_dashboard()

if gdf is None or df_mercado is None:
    st.error("❌ Falha crítica: Dados não carregados. Verifique se o ETL rodou.")
    st.stop()

# --- SIDEBAR (FILTROS) ---
st.sidebar.image("https://cdn-icons-png.flaticon.com/512/2991/2991474.png", width=50)
st.sidebar.title("GridScope Core")
st.sidebar.divider()

# --- CORREÇÃO APLICADA AQUI ---
# Só mostramos na lista as subestações que REALMENTE existem no mapa (GDF)
# Isso elimina as subestações que não geraram Voronoi ou foram filtradas no ETL
subs_no_mapa = gdf["NOM"].unique()

# Filtra o dataframe de dados para conter apenas o que tem no mapa
df_mercado = df_mercado[df_mercado["subestacao"].isin(subs_no_mapa)]

lista_subs = sorted(df_mercado["subestacao"].unique())
escolha = st.sidebar.selectbox("Selecione a Subestação:", lista_subs)
# ------------------------------

# Input de Data Unificado
data_analise = st.sidebar.date_input("Data da Análise:", date.today())
modo = "Auditoria (Histórico)" if data_analise < date.today() else "Operação (Tempo Real/Prev)"
st.sidebar.info(f"Modo Atual: {modo}")

# --- FILTRAGEM DE DADOS ---
area_sel = gdf[gdf["NOM"] == escolha]
try:
    dados_raw = df_mercado[df_mercado["subestacao"] == escolha].iloc[0]
except IndexError:
    st.error(f"Dados não encontrados para {escolha}")
    st.stop()

metricas = dados_raw.get("metricas_rede", {})
dados_gd = dados_raw.get("geracao_distribuida", {})
perfil = dados_raw.get("perfil_consumo", {})

if not area_sel.empty:
    centroid = area_sel.geometry.centroid.iloc[0]
    lat_c, lon_c = centroid.y, centroid.x
else:
    lat_c, lon_c = -10.9472, -37.0731

# --- CONTEÚDO PRINCIPAL ---
st.title(f"Monitoramento: {escolha}")
st.markdown(f"**Localização:** Aracaju - SE | **Status:** Conectado")

# --- ROW 1: KPIs ---
st.header("Infraestrutura de Rede")
k1, k2, k3, k4 = st.columns(4)
with k1: st.metric("Total de Clientes", f"{metricas.get('total_clientes', 0):,}".replace(",", "."))
with k2: st.metric("Consumo Anual", f"{formatar_br(metricas.get('consumo_anual_mwh', 0))} MWh")
with k3: st.metric("Usinas Ativas (GD)", f"{dados_gd.get('total_unidades', 0)}")
with k4: st.metric("Potência Solar", f"{formatar_br(dados_gd.get('potencia_total_kw', 0))} kW")

st.divider()

# --- ROW 2: BARRAS E SIMULAÇÃO ---
col_left, col_right = st.columns([1, 1])

with col_left:
    st.subheader("📊 Potência da GD Instalada")
    detalhe_gd = dados_gd.get("detalhe_por_classe", {})
    if detalhe_gd:
        fig_barras = go.Figure(data=[go.Bar(
            x=list(detalhe_gd.keys()), 
            y=list(detalhe_gd.values()),
            marker_color='#1f77b4',
            text=[f"{v:.1f} kW" for v in detalhe_gd.values()],
            textposition='auto'
        )])
        fig_barras.update_layout(height=350, margin=dict(l=10,r=10,t=30,b=10), yaxis_title="kW")
        st.plotly_chart(fig_barras, use_container_width=True)
    else:
        st.info("Sem dados detalhados de GD.")

with col_right:
    st.subheader(f"☀️ Simulação VPP: {data_analise.strftime('%d/%m/%y')}")
    dados_sim = consultar_simulacao(escolha, data_analise)
    if dados_sim:
        sc1, sc2 = st.columns(2)
        sc1.write(f"**Clima:** {dados_sim.get('condicao_tempo')}")
        sc1.write(f"**Irradiação:** {dados_sim.get('irradiacao_solar_kwh_m2')} kWh/m²")
        sc2.write(f"**Temp. Máx:** {dados_sim.get('temperatura_max_c')}°C")
        sc2.write(f"**Perda Térmica:** {dados_sim.get('fator_perda_termica')}%")
        impacto = dados_sim.get("impacto_na_rede", "NORMAL")
        
        if "CRITICO" in impacto.upper() or "ALTA" in impacto.upper():
            st.error(f"Alerta: {impacto}")
        else:
            st.success(f"Status: {impacto}")
    else:
        st.warning("⚠️ Serviço de Simulação Solar Offline (Porta 8000).")

st.divider()

# --- ROW 3: IA DUCK CURVE (AUTOMÁTICO) ---
st.header("🧠 Análise Preditiva (AI Duck Curve)")

with st.spinner(f"🤖 IA: Recalculando fluxo energético para {data_analise.strftime('%d/%m')}..."):
    
    res_ia, erro_ia = obter_previsao_ia_cached(
        subestacao=escolha,
        data_str=str(data_analise),
        potencia_gd=dados_gd.get('potencia_total_kw', 0),
        lat=lat_c,
        lon=lon_c
    )

    if res_ia:
        if 'timeline' in res_ia and 'consumo_mwh' in res_ia:
            # Box de Status da Análise
            cor_alerta = "#dc3545" if res_ia.get('alerta', False) else "#28a745"
            analise_texto = res_ia.get('analise', 'Análise processada')
            st.markdown(f"""
                <div style='background-color:{cor_alerta}; color:white; padding:12px; border-radius:8px; text-align:center; margin-bottom: 15px;'>
                    <h5 style='margin:0;'>{analise_texto}</h5>
                </div>
            """, unsafe_allow_html=True)

            # Gráfico Principal
            fig_duck = go.Figure()
            
            # Área de Consumo
            fig_duck.add_trace(go.Scatter(
                x=res_ia['timeline'], y=res_ia['consumo_mwh'], 
                name="Carga (Consumo)", fill='tozeroy', 
                line=dict(color='#007bff', width=2), fillcolor='rgba(0, 123, 255, 0.1)'
            ))
            
            # Linha Solar
            fig_duck.add_trace(go.Scatter(
                x=res_ia['timeline'], y=res_ia['geracao_mwh'], 
                name="Geração Solar", line=dict(color='#ffc107', width=3)
            ))
            
            # Carga Líquida
            fig_duck.add_trace(go.Scatter(
                x=res_ia['timeline'], y=res_ia['carga_liquida_mwh'], 
                name="Carga Líquida (Saldo)", line=dict(color='white', dash='dot', width=2)
            ))
            
            # Linha de Zero (Fluxo Reverso)
            fig_duck.add_hline(y=0, line_dash="solid", line_color="#dc3545", annotation_text="Limite Reverso")
            
            fig_duck.update_layout(
                height=450, 
                title=dict(text=f"Projeção Energética: {data_analise.strftime('%d/%m/%Y')}", x=0),
                hovermode="x unified", legend=dict(orientation="h", y=1.1)
            )
            st.plotly_chart(fig_duck, use_container_width=True)

            # KPIs Adicionais
            kp1, kp2, kp3 = st.columns(3)
            pico_solar = max(res_ia['geracao_mwh'])
            min_liquida = min(res_ia['carga_liquida_mwh'])
            
            # Cálculo de Autossuficiência
            cons_tot = sum(res_ia['consumo_mwh'])
            ger_tot = sum(res_ia['geracao_mwh'])
            cobertura = (ger_tot / cons_tot * 100) if cons_tot > 0 else 0

            kp1.metric("Pico de Geração Solar", f"{pico_solar:.2f} MW")
            kp2.metric("Menor Carga Líquida", f"{min_liquida:.2f} MW", delta="Crítico" if min_liquida < 0 else "Estável", delta_color="inverse")
            kp3.metric("Cobertura Solar Diária", f"{cobertura:.1f}%")

        else:
            st.error("Dados incompletos retornados pela IA.")
    else:
        st.warning(f"Não foi possível calcular a curva. Detalhe: {erro_ia}")

# --- ROW 4: PERFIL E GEOLOCALIZAÇÃO ---
col_pie, col_map = st.columns([1, 2])

with col_pie:
    st.subheader("Segmentação")
    dados_pie = [{"Segmento": k, "Qtd": v["qtd_clientes"]} for k, v in perfil.items() if k in CATEGORIAS_ALVO]
    df_pie = pd.DataFrame(dados_pie)
    if not df_pie.empty:
        fig_pie = px.pie(df_pie, values="Qtd", names="Segmento", hole=0.4, color="Segmento", color_discrete_map=CORES_MAPA)
        fig_pie.update_layout(margin=dict(t=30, b=0, l=0, r=0), height=350)
        st.plotly_chart(fig_pie, use_container_width=True)
    else:
        st.info("Sem dados de segmentação.")

with col_map:
    st.subheader("Território de Atendimento")
    m = folium.Map(location=[lat_c, lon_c], zoom_start=13)

    def style_fn(feature):
        nome = feature['properties']['NOM']
        is_sel = (nome == escolha)
        dado_s = df_mercado[df_mercado['subestacao'] == nome]
        critic = dado_s.iloc[0].get('metricas_rede', {}).get('nivel_criticidade_gd', 'BAIXO') if not dado_s.empty else "BAIXO"
        cor = {'BAIXO': '#2ecc71', 'MEDIO': '#f1c40f', 'ALTO': '#e74c3c'}.get(critic, '#2ecc71')
        return {'fillColor': cor, 'color': 'white' if is_sel else 'gray', 'weight': 3 if is_sel else 1, 'fillOpacity': 0.7 if is_sel else 0.3}

    folium.GeoJson(gdf, style_function=style_fn, tooltip=folium.GeoJsonTooltip(fields=["NOM"], aliases=["Subestação:"])).add_to(m)
    st_folium(m, use_container_width=True, height=400)
    
# --- ROW 5: TABELA DETALHADA E RECOMENDAÇÕES (NOVO) ---
st.divider()
st.header("📋 Relatório Técnico & Ações")

col_table, col_actions = st.columns([2, 1])

with col_table:
    st.subheader("Dados Consolidados")
    dados_consolidados = {
        "Parâmetro": [
            "Subestação Alvo",
            "Consumo Anual Total",
            "Potência GD Instalada",
            "Qtd. Usinas Solares",
            "Total Clientes",
            "Criticidade da Rede"
        ],
        "Valor": [
            str(escolha),
            f"{formatar_br(metricas.get('consumo_anual_mwh', 0))} MWh",
            f"{formatar_br(dados_gd.get('potencia_total_kw', 0))} kW",
            f"{dados_gd.get('total_unidades', 0)} unid.",
            f"{metricas.get('total_clientes', 0)}",
            metricas.get('nivel_criticidade_gd', 'NORMAL')
        ]
    }
    df_view = pd.DataFrame(dados_consolidados)
    st.dataframe(
        df_view, 
        use_container_width=True, 
        hide_index=True,
        column_config={
            "Parâmetro": st.column_config.TextColumn("Indicador", width="medium"),
            "Valor": st.column_config.TextColumn("Medição Atual", width="medium")
        }
    )

with col_actions:
    st.subheader("Diagnóstico Automático")
    
    potencia_kw = dados_gd.get('potencia_total_kw', 0)
    geracao_est_mwh = (potencia_kw * 4.5 * 365) / 1000
    consumo_mwh = metricas.get('consumo_anual_mwh', 1) 
    
    penetracao = (geracao_est_mwh / consumo_mwh) * 100
    
    st.write(f"**Nível de Penetração GD:** {penetracao:.1f}%")
    
    if penetracao > 25:
        st.warning("⚠️ **Saturação Alta:** Risco de inversão de fluxo. Recomenda-se estudo de baterias (BESS).")
    elif penetracao > 10:
        st.info("ℹ️ **Atenção:** Monitorar horários de pico solar (11h-13h).")
    else:
        st.success("✅ **Rede Estável:** Capacidade disponível para novas conexões.")

    csv = df_view.to_csv(index=False).encode('utf-8')
    st.download_button(
        label="📥 Baixar Relatório CSV",
        data=csv,
        file_name=f"relatorio_{escolha}_{date.today()}.csv",
        mime="text/csv",
        use_container_width=True
    )

st.caption(f"GridScope v4.6 Enterprise | Dados atualizados em: {date.today().strftime('%d/%m/%Y')}")