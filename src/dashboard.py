import streamlit as st
import sys
import os

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from views import analise_subestacao, visao_geral

st.set_page_config(
    page_title="GridScope - Inteligência Energética",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="expanded"
)

st.markdown("""
    <style>
        .stApp { background-color: #0e1117; }
        section[data-testid="stSidebar"] { background-color: #161b22; }
    </style>
""", unsafe_allow_html=True)

st.sidebar.image("https://img.icons8.com/fluency/96/lightning-bolt.png", width=60)
st.sidebar.title("GridScope")
st.sidebar.markdown("---")

navegacao = st.sidebar.radio(
    "Navegue pelo Sistema:",
    ["🔍 Análise por Subestação (IA)", "📊 Visão Geral"]
)

st.sidebar.markdown("---")
st.sidebar.caption("Hackathon Edition v1.0")

if navegacao == "🔍 Análise por Subestação (IA)":
    try:
        analise_subestacao.render_view()
    except Exception as e:
        st.error(f"Erro ao carregar módulo de Análise: {e}")

elif navegacao == "📊 Visão Geral (Executivo)":
    try:
        visao_geral.render_view()
    except Exception as e:
        st.error(f"Erro ao carregar módulo de Visão Geral: {e}")