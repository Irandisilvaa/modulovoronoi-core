import streamlit as st
import plotly.graph_objects as go
import requests
import urllib.parse
import sys
import os

try:
    from utils import limpar_float
except ImportError:
    sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    try:
        from utils import limpar_float
    except ImportError:
        def limpar_float(val):
            try:
                if isinstance(val, (int, float)): return float(val)
                return float(str(val).replace(',', '.')) if val else 0.0
            except:
                return 0.0

def consultar_simulacao(subestacao_id, data_escolhida):
    """
    Consulta a API de Simulação Solar (Porta 8000).
    """
    data_str = data_escolhida.strftime("%d-%m-%Y")
    id_seguro = urllib.parse.quote(str(subestacao_id))
    
    url = f"http://127.0.0.1:8000/simulacao/{id_seguro}?data={data_str}"

    try:
        response = requests.get(url, timeout=5)
        if response.status_code == 200:
            return response.json()
        return None
    except Exception:
        return None

def consultar_ia_predict(payload):
    """
    Consulta a API de Inteligência Artificial (Porta 8001).
    """
    try:
        resp = requests.post(
            "http://127.0.0.1:8001/predict/duck-curve",
            json=payload,
            timeout=8
        )
        if resp.status_code == 200:
            return resp.json(), None
        elif resp.status_code == 422:
            return None, "Erro 422: Dados inválidos enviados para a IA."
        else:
            return None, f"Erro na API: {resp.status_code}"
    except requests.exceptions.ConnectionError:
        return None, "Serviço de IA Offline (Porta 8001)"
    except Exception as e:
        return None, str(e)

def render_tab_ia(subestacao_obj, data_analise, dados_gd):
    """
    Renderiza todo o conteúdo da aba de Inteligência Artificial.
    Recebe:
        - subestacao_obj: dict com 'id' e 'nome'
        - data_analise: objeto date
        - dados_gd: dicionário com dados de geração distribuída
    """
    st.subheader(f"☀️ Simulação VPP & Duck Curve: {data_analise.strftime('%d/%m/%Y')}")

    dados_sim = consultar_simulacao(subestacao_obj["id"], data_analise)

    if dados_sim:
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Clima", dados_sim.get('condicao_tempo', '--'))
        c2.metric("Irradiação", f"{dados_sim.get('irradiacao_solar_kwh_m2', 0)} kWh/m²")
        c3.metric("Temp. Máx", f"{dados_sim.get('temperatura_max_c', 0)}°C")
        c4.metric("Perda Térmica", f"{dados_sim.get('fator_perda_termica', 0)}%")

        impacto = dados_sim.get("impacto_na_rede", "NORMAL")
        if "CRITICO" in str(impacto).upper() or "ALTA" in str(impacto).upper():
            st.error(f"🚨 Previsão de Impacto na Rede: {impacto}")
        else:
            st.success(f"✅ Previsão de Impacto na Rede: {impacto}")
    else:
        st.warning("⚠️ API de Simulação (VPP) não respondeu. Verifique a porta 8000.")

    st.divider()

    st.header("🧠 Análise Preditiva (AI Duck Curve)")
    
    with st.spinner(f"IA processando fluxo de carga para {subestacao_obj['nome']}..."):
        
        potencia_kw = limpar_float(dados_gd.get("potencia_total_kw", 0))
        capacidade_mw = float(potencia_kw / 1000)

        payload_duck = {
            "subestacao_id": str(subestacao_obj["id"]),
            "data_alvo": data_analise.isoformat(),
            "capacidade_gd_mw": capacidade_mw,
            "fator_sol": 0.85
        }

        res_ia, erro_ia = consultar_ia_predict(payload_duck)

        if res_ia:
            if 'timeline' in res_ia and 'consumo_mwh' in res_ia and len(res_ia['timeline']) > 0:
                analise_texto = res_ia.get('analise', 'Análise processada com sucesso.')
                is_alerta = res_ia.get('alerta', False)

                if is_alerta:
                    st.error(f"**ALERTA DA IA:** {analise_texto}", icon="⚠️")
                else:
                    st.success(f"**DIAGNÓSTICO:** {analise_texto}", icon="✅")
                fig_duck = go.Figure()
                
                fig_duck.add_trace(go.Scatter(
                    x=res_ia['timeline'], 
                    y=res_ia['consumo_mwh'], 
                    name="Carga (Consumo)",
                    fill='tozeroy', 
                    line=dict(color='#007bff', width=2),
                    fillcolor='rgba(0, 123, 255, 0.1)'
                ))
                
                fig_duck.add_trace(go.Scatter(
                    x=res_ia['timeline'], 
                    y=res_ia['geracao_mwh'], 
                    name="Geração Solar (Simulada)",
                    line=dict(color="#ff7e14", width=3)
                ))
                
                fig_duck.add_trace(go.Scatter(
                    x=res_ia['timeline'], 
                    y=res_ia['carga_liquida_mwh'], 
                    name="Carga Líquida (Saldo)",
                    line=dict(color="#ffffff", dash='dot', width=3)
                ))
                
                fig_duck.add_hline(y=0, line_dash="solid", line_color="#17008a", annotation_text="Limite de Inversão")
                
                fig_duck.update_layout(
                    height=500, 
                    title="Projeção Energética Horária (24h)", 
                    hovermode="x unified",
                    legend=dict(orientation="h", y=1.1, x=0),
                    yaxis_title="Potência (MW)",
                    xaxis_title="Horário"
                )
                
                st.plotly_chart(fig_duck, use_container_width=True)

                kp1, kp2, kp3 = st.columns(3)
                
                min_liquida = min(res_ia['carga_liquida_mwh']) if res_ia.get('carga_liquida_mwh') else 0
                ger_tot = sum(res_ia['geracao_mwh']) if res_ia.get('geracao_mwh') else 0
                pico_sol = max(res_ia['geracao_mwh']) if res_ia.get('geracao_mwh') else 0
                
                kp1.metric("Pico Solar Estimado", f"{pico_sol:.2f} MW")
                kp2.metric("Mínima Carga Líquida", f"{min_liquida:.2f} MW", 
                           delta="Risco Inversão" if min_liquida < 0 else "Seguro", 
                           delta_color="inverse")
                kp3.metric("Energia Solar Total (Dia)", f"{ger_tot:.2f} MWh")

            else:
                st.error("A IA retornou dados, mas o formato está incompleto (timeline ausente).")
        else:
            st.warning(f"Não foi possível gerar a Curva Pato. {erro_ia}")