import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import folium
from streamlit_folium import st_folium
import requests
import os
import sys
import ast
import urllib.parse
from datetime import date, timedelta
import warnings

API_URL = "http://localhost:8001/predict/duck-curve"

# --- SUPRESSÃO DE AVISOS (CLEAN LOGS) ---
# Ignora avisos de depreciação do Streamlit e alertas de geometria do GeoPandas que não afetam a lógica
warnings.filterwarnings("ignore", category=UserWarning)
warnings.filterwarnings("ignore", message=".*use_container_width.*")

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
    if isinstance(valor, str): return valor
    try:
        return f"{float(valor):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    except:
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

def limpar_float(valor):
    """
    Converte qualquer formato de número (texto com vírgula, ponto, etc) para float.
    """
    if isinstance(valor, (int, float)):
        return float(valor)
    if isinstance(valor, str):
        val_limpo = valor.replace("R$", "").strip()
        try:
            if "," in val_limpo and "." in val_limpo:
                val_limpo = val_limpo.replace(".", "").replace(",", ".")
            elif "," in val_limpo:
                val_limpo = val_limpo.replace(",", ".")
            return float(val_limpo)
        except ValueError:
            return 0.0
    return 0.0

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
    """Consulta API de Simulação Solar (Backend 8000) com tratamento de erro detalhado."""
    
    # 1. Formata a data para envio (string)
    data_str = data_escolhida.strftime("%d-%m-%Y")
    
    # 2. Codifica o nome para URL (resolve problemas com espaços e parênteses)
    nome_seguro = urllib.parse.quote(str(subestacao).strip())
    
    url = f"http://127.0.0.1:8000/simulacao/{nome_seguro}?data={data_str}"
    
    try:
        # Timeout de 10s para garantir conexões lentas
        response = requests.get(url, timeout=10)
        
        # Se a API responder, retorna o JSON
        if response.status_code == 200:
            return response.json()
        
        # Se der erro 404 ou 500, loga mas não quebra o dashboard
        else:
            return None

    except requests.exceptions.ConnectionError:
        return None
    except requests.exceptions.Timeout:
        return None
    except Exception as e:
        return None

def consultar_ia_predict(payload):
    """Consulta crua à API de Inteligência Artificial (Backend 8001)."""
    try:
        resp = requests.post(
            "http://127.0.0.1:8001/predict/duck-curve",
            json=payload,
            timeout=8
        )
        if resp.status_code == 200:
            return resp.json(), None
        elif resp.status_code == 422:
            return None, f"Erro 422: Dados inválidos (API recusou payload)."
        else:
            return None, f"Erro na API: {resp.status_code}"
    except requests.exceptions.ConnectionError:
        return None, "Serviço de IA Offline (Porta 8001)"
    except Exception as e:
        return None, str(e)

@st.cache_data(ttl=3600, show_spinner=False)
def obter_previsao_ia_cached(subestacao_nome, subestacao_id, data_str, consumo_mensal_mwh, potencia_gd_kw, lat, lon):
    """
    Chama a API de Inteligência Artificial para gerar a Duck Curve.
    Agora envia o ID para carregar o modelo específico (DNA da Carga).
    """
    # Payload exato que a API (DuckCurveInput) espera
    payload = {
        "data_alvo": str(data_str),
        "potencia_gd_kw": float(potencia_gd_kw),
        "consumo_mes_alvo_mwh": float(consumo_mensal_mwh),
        "lat": float(lat),
        "lon": float(lon),
        "subestacao_id": str(subestacao_id) # <--- O PULO DO GATO: Envia o ID para usar a IA treinada
    }

    try:
        response = requests.post(API_URL, json=payload, timeout=10)
        
        if response.status_code == 200:
            return response.json(), None
        else:
            return None, f"Erro API: {response.status_code} - {response.text}"
            
    except requests.exceptions.ConnectionError:
        return None, "API Offline. Verifique se o 'server.py' está rodando."
    except Exception as e:
        return None, f"Erro de conexão: {e}"

# --- CARREGAMENTO INICIAL ---
gdf, df_mercado = obter_dados_dashboard()

if gdf is None or df_mercado is None:
    st.error("❌ Falha crítica: Dados não carregados. Verifique se o ETL rodou.")
    st.stop()

# --- SIDEBAR (FILTROS) ---
st.sidebar.image("https://cdn-icons-png.flaticon.com/512/2991/2991474.png", width=50)
st.sidebar.title("GridScope Core")
st.sidebar.divider()

mapa_opcoes = {}
# Varre o DataFrame para garantir que só mostramos o que existe
if 'subestacao' in df_mercado.columns:
    for idx, row in df_mercado.iterrows():
        # Tenta pegar ID tecnico se existir, senão usa indice
        id_tec = row.get('id_tecnico', idx) 
        label = row['subestacao'] # Ex: "ATALAIA (ID: 15)"
        mapa_opcoes[label] = id_tec

if not mapa_opcoes:
    st.warning("Nenhuma subestação disponível nos dados de mercado.")
    st.stop()

escolha_label = st.sidebar.selectbox("Selecione a Subestação:", sorted(mapa_opcoes.keys()))
id_escolhido = mapa_opcoes[escolha_label]

data_analise = st.sidebar.date_input("Data da Análise:", date.today())
modo = "Auditoria (Histórico)" if data_analise < date.today() else "Operação (Tempo Real/Prev)"
st.sidebar.info(f"Modo Atual: {modo}")

# --- FILTRAGEM DE DADOS ---
# 1. Tenta achar no mapa (GDF)
area_sel = gdf[gdf["COD_ID"].astype(str) == str(id_escolhido)]

centroid_existe = False
if not area_sel.empty:
    centroid_existe = True
    try:
        centroid = area_sel.to_crs(epsg=3857).geometry.centroid.to_crs(area_sel.crs).iloc[0]
        lat_c, lon_c = centroid.y, centroid.x
    except Exception:
        # Fallback simples se a projeção falhar
        c = area_sel.geometry.centroid.iloc[0]
        lat_c, lon_c = c.y, c.x
else:
    # Coordenadas padrão (Aracaju) se não achar geometria
    lat_c, lon_c = -10.9472, -37.0731

# 2. Busca dados de mercado (JSON)
try:
    if 'id_tecnico' in df_mercado.columns:
          dados_filtrados = df_mercado[df_mercado["id_tecnico"].astype(str) == str(id_escolhido)]
    else:
          dados_filtrados = df_mercado[df_mercado["subestacao"] == escolha_label]

    if dados_filtrados.empty:
        # Fallback de emergência
        dados_filtrados = df_mercado.iloc[[0]]
    
    dados_raw = dados_filtrados.iloc[0]
    # Limpa nome visualmente
    nome_limpo_escolha = str(dados_raw["subestacao"]).split(' (ID:')[0]

except Exception as e:
    st.error(f"Erro ao recuperar dados da tabela: {e}")
    st.stop()

# --- CONVERSÃO SEGURA DE TIPOS ---
metricas = converter_para_dict(dados_raw.get("metricas_rede", {}))
dados_gd = converter_para_dict(dados_raw.get("geracao_distribuida", {}))
perfil = converter_para_dict(dados_raw.get("perfil_consumo", {}))

# --- CABEÇALHO GLOBAL ---
st.title(f"Monitoramento: {nome_limpo_escolha}")
st.caption(f"ID Técnico: {id_escolhido}")
st.markdown(f"**Localização:** Aracaju - SE | **Status:** Conectado")

# --- ROW 1: KPIs (Sempre Visíveis) ---
st.header("Infraestrutura de Rede")
k1, k2, k3, k4 = st.columns(4)
with k1: st.metric("Total de Clientes", f"{metricas.get('total_clientes', 0):,}".replace(",", "."))
with k2: st.metric("Consumo Anual", f"{formatar_br(metricas.get('consumo_anual_mwh', 0))} MWh")
with k3: st.metric("Usinas Ativas (GD)", f"{dados_gd.get('total_unidades', 0)}")
with k4: st.metric("Potência Solar Instalada", f"{formatar_br(dados_gd.get('potencia_total_kw', 0))} kW")

st.divider()

tab_visao_geral, tab_ia = st.tabs(["📊 Visão Geral & Perfil", "🧠 Inteligência Artificial & Simulação"])

# --- ABA 1: VISÃO GERAL ---
with tab_visao_geral:
    st.subheader("Potência da GD Instalada por Classe")

    detalhe_raw = converter_para_dict(dados_gd.get("detalhe_por_classe", {}))
    
    detalhe_gd = {k: v for k, v in detalhe_raw.items() if k in CATEGORIAS_ALVO}
    
    if detalhe_gd:
        fig_barras = go.Figure(data=[go.Bar(
            x=list(detalhe_gd.keys()), 
            y=list(detalhe_gd.values()),
            marker_color='#1f77b4',
            text=[f"{v:,.1f} kW".replace(",", "X").replace(".", ",").replace("X", ".") for v in detalhe_gd.values()],
            textposition='auto'
        )])
        fig_barras.update_layout(height=250, margin=dict(l=10,r=10,t=10,b=10), yaxis_title="kW")
        st.plotly_chart(fig_barras, use_container_width=True)
    else:
        st.info("Sem dados de GD para as categorias selecionadas.")

    st.divider()
    
    # --- PARTE 2: Mapa de Cobertura (Largura Total) ---
    st.subheader("📍 Área de Cobertura Geográfica")
    
    if centroid_existe:
        m = folium.Map(location=[lat_c, lon_c], zoom_start=13)

        def style_fn(feature):
            feature_id = feature['properties'].get('COD_ID')
            # Comparação segura string vs string
            is_sel = (str(feature_id) == str(id_escolhido))
            cor = '#007bff' if is_sel else 'gray' 
            return {'fillColor': cor, 'color': 'white' if is_sel else 'gray', 'weight': 3 if is_sel else 1, 'fillOpacity': 0.7 if is_sel else 0.3}

        folium.GeoJson(gdf, style_function=style_fn, tooltip=folium.GeoJsonTooltip(fields=["NOM", "COD_ID"], aliases=["Subestação:", "ID:"])).add_to(m)
        st_folium(m, use_container_width=True, height=400)
    else:
        st.warning("⚠️ Geometria não encontrada para este ID. Mapa indisponível.")

    st.divider()

    # --- PARTE 3: Gráficos de Perfil (Lado a Lado - 50% cada) ---
    st.subheader("📌 Segmentação de Mercado")
    
    col_graf1, col_graf2 = st.columns(2)

    # ESQUERDA: PIZZA (Clientes)
    with col_graf1:
        st.markdown("**Distribuição de Clientes (Qtd)**")
        dados_pie = []
        for k, v in perfil.items():
            if k in CATEGORIAS_ALVO:
                v_dict = converter_para_dict(v)
                val = v_dict.get("qtd_clientes", 0)
                if val > 0:
                    dados_pie.append({"Segmento": k, "Valor": val})
                
        df_pie = pd.DataFrame(dados_pie)
        if not df_pie.empty:
            fig_pie = px.pie(df_pie, values="Valor", names="Segmento", hole=0.4, color="Segmento", color_discrete_map=CORES_MAPA)
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

    # DIREITA: BARRAS 
    with col_graf2:
        st.markdown("**Carga por Classe (Consumo MWh)**")
        dados_carga = []
        
        if perfil:
            for k, v in perfil.items():
                if k not in CATEGORIAS_ALVO: 
                     continue
                chave_limpa = k.strip()
                v_dict = converter_para_dict(v)
                
                # Prioriza 'consumo_anual_mwh', fallback 'ENE_12'
                val_candidato = (v_dict.get("consumo_anual_mwh") or v_dict.get("ENE_12") or 0)
                val_float = limpar_float(val_candidato)
                
                if val_float > 0:
                    dados_carga.append({"Segmento": chave_limpa, "Valor": val_float})
        
        df_carga = pd.DataFrame(dados_carga)
        
        if not df_carga.empty:
            df_carga = df_carga.sort_values(by="Valor", ascending=False)
            
            fig_carga = go.Figure(data=[
                go.Bar(
                    x=df_carga["Segmento"],
                    y=df_carga["Valor"],
                    marker_color=[CORES_MAPA.get(s, '#17a2b8') for s in df_carga["Segmento"]],
                    text=[f"{val:,.0f} MWh".replace(",", "X").replace(".", ",").replace("X", ".") for val in df_carga["Valor"]],
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
            st.warning("Gráfico vazio. O consumo anual está zerado no arquivo JSON.")

    st.divider()
    
    # Tabela e Relatório
    st.header("📋 Relatório Técnico & Ações")
    col_table, col_actions = st.columns([2, 1])

    with col_table:
        st.subheader("Dados Consolidados")
        dados_consolidados = {
            "Parâmetro": [
                "Subestação Alvo", "ID Técnico", "Consumo Anual Total", 
                "Potência GD Instalada", "Qtd. Usinas Solares", 
                "Total Clientes", "Criticidade da Rede"
            ],
            "Valor": [
                str(nome_limpo_escolha), str(id_escolhido),
                f"{formatar_br(metricas.get('consumo_anual_mwh', 0))} MWh",
                f"{formatar_br(dados_gd.get('potencia_total_kw', 0))} kW",
                f"{dados_gd.get('total_unidades', 0)} unid.",
                f"{metricas.get('total_clientes', 0)}",
                metricas.get('nivel_criticidade_gd', 'NORMAL')
            ]
        }
        st.dataframe(pd.DataFrame(dados_consolidados), use_container_width=True, hide_index=True)

    with col_actions:
        st.subheader("Diagnóstico Automático")
        potencia_kw = limpar_float(dados_gd.get('potencia_total_kw', 0))
        geracao_est_mwh = (potencia_kw * 4.5 * 365) / 1000
        consumo_mwh = limpar_float(metricas.get('consumo_anual_mwh', 1))
        
        if consumo_mwh == 0: consumo_mwh = 1
        
        penetracao = (geracao_est_mwh / consumo_mwh) * 100
        st.write(f"**Nível de Penetração GD:** {penetracao:.1f}%")
        
        if penetracao > 25:
            st.warning("⚠️ **Saturação Alta:** Risco de inversão de fluxo.")
        elif penetracao > 10:
            st.info("ℹ️ **Atenção:** Monitorar horários de pico.")
        else:
            st.success("✅ **Rede Estável:** Capacidade disponível.")

        csv = pd.DataFrame(dados_consolidados).to_csv(index=False).encode('utf-8')
        st.download_button(label="📥 Baixar Relatório CSV", data=csv, file_name=f"relatorio_{id_escolhido}.csv", mime="text/csv", use_container_width=True)

# --- ABA 2: INTELIGÊNCIA ARTIFICIAL ---
with tab_ia:
    st.subheader(f"☀️ Simulação VPP & Duck Curve: {data_analise.strftime('%d/%m/%Y')}")
    
    # Simulação VPP (Safe Mode)
    dados_sim = consultar_simulacao(nome_limpo_escolha, data_analise)
    
    if dados_sim:
        sc1, sc2, sc3, sc4 = st.columns(4)
        sc1.metric("Clima", dados_sim.get('condicao_tempo', '--'))
        sc2.metric("Irradiação", f"{dados_sim.get('irradiacao_solar_kwh_m2', 0)} kWh/m²")
        sc3.metric("Temp. Máx", f"{dados_sim.get('temperatura_max_c', 0)}°C")
        sc4.metric("Perda Térmica", f"{dados_sim.get('fator_perda_termica', 0)}%")
        
        impacto = dados_sim.get("impacto_na_rede", "NORMAL")
        if "CRITICO" in str(impacto).upper() or "ALTA" in str(impacto).upper():
            st.error(f"🚨 Status da Rede: {impacto}")
        else:
            st.success(f"✅ Status da Rede: {impacto}")
    else:
        st.warning("⚠️ VPP Offline ou não conectou (Porta 8000). Verifique o terminal para ver o erro detalhado.")

    st.divider()

    st.header("🧠 Análise Preditiva (AI Duck Curve)")

# --- PREPARAÇÃO DOS DADOS ---
# Tenta pegar o ID. Se não tiver, usa o nome como fallback (mas o ideal é ter o ID numérico/código)
id_para_ia = dados_gd.get('id', nome_limpo_escolha) 

# Define um consumo padrão caso o usuário não tenha inputado (ex: média do ano)
consumo_para_ia = consumo_mes_estimado if 'consumo_mes_estimado' in locals() else 500.0

with st.spinner(f"IA: Simulando perfil de carga para {nome_limpo_escolha}..."):
    
    # --- CHAMADA ATUALIZADA ---
    res_ia, erro_ia = obter_previsao_ia_cached(
        subestacao_nome=nome_limpo_escolha,
        subestacao_id=id_para_ia,          # <--- NOVO: Passando o ID
        data_str=str(data_analise),
        consumo_mensal_mwh=consumo_para_ia, # <--- NOVO: Passando o volume mensal
        potencia_gd_kw=dados_gd.get('potencia_total_kw', 0),
        lat=lat_c,
        lon=lon_c
    )

    if res_ia:
        # ... (O resto do seu código de plotagem continua IGUAL) ...
        if 'timeline' in res_ia and 'consumo_mwh' in res_ia and len(res_ia['timeline']) > 0:
            analise_texto = res_ia.get('analise', 'Análise processada')
            is_alerta = res_ia.get('alerta', False)
            
            # Exibe metadados para você confirmar que funcionou
            meta = res_ia.get('metadados', {})
            origem_perfil = meta.get('origem_perfil', 'Desconhecida')
            
            if is_alerta:
                st.error(f"**ALERTA:** {analise_texto} (Fonte: {origem_perfil})", icon="⚠️")
            else:
                st.success(f"**NORMAL:** {analise_texto} (Fonte: {origem_perfil})", icon="✅")

            fig_duck = go.Figure()
            # ... (Seu código de gráfico existente) ...
            fig_duck.add_trace(go.Scatter(x=res_ia['timeline'], y=res_ia['consumo_mwh'], name="Carga (Consumo)", fill='tozeroy', line=dict(color='#007bff', width=2), fillcolor='rgba(0, 123, 255, 0.1)'))
            fig_duck.add_trace(go.Scatter(x=res_ia['timeline'], y=res_ia['geracao_mwh'], name="Geração Solar", line=dict(color='#ffc107', width=3)))
            fig_duck.add_trace(go.Scatter(x=res_ia['timeline'], y=res_ia['carga_liquida_mwh'], name="Carga Líquida (Saldo)", line=dict(color='white', dash='dot', width=2)))
            fig_duck.add_hline(y=0, line_dash="solid", line_color="#dc3545", annotation_text="Limite Reverso")
            fig_duck.update_layout(height=500, title="Projeção Energética (24h)", hovermode="x unified", legend=dict(orientation="h", y=1.1))
            st.plotly_chart(fig_duck, use_container_width=True)

            # KPIs
            kp1, kp2, kp3 = st.columns(3)
            pico_solar = max(res_ia['geracao_mwh']) if res_ia['geracao_mwh'] else 0
            min_liquida = min(res_ia['carga_liquida_mwh']) if res_ia['carga_liquida_mwh'] else 0
            cons_tot = sum(res_ia['consumo_mwh']) if res_ia['consumo_mwh'] else 0
            ger_tot = sum(res_ia['geracao_mwh']) if res_ia['geracao_mwh'] else 0
            cobertura = (ger_tot / cons_tot * 100) if cons_tot > 0 else 0

            kp1.metric("Pico Solar", f"{pico_solar:.2f} MW")
            kp2.metric("Mínima Líquida", f"{min_liquida:.2f} MW", delta="Crítico" if min_liquida < 0 else "Estável", delta_color="inverse")
            kp3.metric("Cobertura Solar", f"{cobertura:.1f}%")

        else:
            st.error("Dados incompletos retornados pela IA.")
    else:
        st.warning(f"⚠️ IA Indisponível: {erro_ia}")

st.caption(f"GridScope v4.9 Enterprise | Dados atualizados em: {date.today().strftime('%d/%m/%Y')}")