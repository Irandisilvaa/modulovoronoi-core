import streamlit as st
import plotly.graph_objects as go
import requests
import urllib.parse
import sys
import os
import numpy as np 

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Tenta importar a função de limpeza, ou define fallback local
try:
    from utils import limpar_float
except ImportError:
    def limpar_float(valor):
        try:
            return float(valor)
        except (ValueError, TypeError):
            return 0.0


def consultar_simulacao(subestacao_id, data_escolhida):
    """
    Consulta a API de Simulação Física/VPP (Porta 8000).
    """
    data_str = data_escolhida.strftime("%d-%m-%Y")
    
    if not subestacao_id or str(subestacao_id).lower() == 'none':
        return None, "ID da Subestação não identificado."

    id_seguro = urllib.parse.quote(str(subestacao_id))
    
    # URL configurada para funcionar tanto em Docker (gridscope_api) quanto local (localhost)
    # Tenta localhost primeiro pois o usuário está rodando no Windows Host
    url = f"http://localhost:8000/simulacao/{id_seguro}?data={data_str}"

    try:
        response = requests.get(url, timeout=5)
        if response.status_code == 200:
            return response.json(), None
        return None, f"Erro {response.status_code}: {response.text[:100]}"
    except Exception as e:
        return None, f"Erro Conexão: {str(e)}"

def consultar_ia_predict(payload):
    """
    Consulta a API de Inteligência Artificial (Porta 8001).
    """
    url = "http://127.0.0.1:8001/predict/duck-curve"
    try:
        resp = requests.post(url, json=payload, timeout=10)
        
        if resp.status_code == 200:
            return resp.json(), None
        elif resp.status_code == 422:
            return None, "Erro 422 (Dados Inválidos): Verifique o formato dos dados enviados."
        else:
            return None, f"Erro API: {resp.status_code} - {resp.text}"
            
    except requests.exceptions.ConnectionError:
        return None, "Serviço de IA Offline (Porta 8001 - Verifique se o backend está rodando)"
    except Exception as e:
        return None, str(e)


def render_tab_ia(subestacao_obj, data_analise, dados_gd):
    """
    Renderiza todo o conteúdo da aba de Inteligência Artificial.
    (Versão com suporte a: geração em y2, gráfico separado para classes,
    recalculo de escala baseado em séries visíveis. Ajustes para garantir
    curvas por classe a partir do total e linhas mais nítidas/grossas. Classes
    com comportamento horário distinto e soma horária igual ao consumo total.)
    """
    st.subheader(f"☀️ Simulação VPP & Duck Curve: {data_analise.strftime('%d/%m/%Y')}")

    # Tenta obter ID ou NOME. O endpoint espera nome ou ID que consiga resolver. 
    identificador = (subestacao_obj.get("NOME") or 
                    subestacao_obj.get("nome") or 
                    subestacao_obj.get("subestacao") or 
                    subestacao_obj.get("COD_ID") or 
                    subestacao_obj.get("id"))
    dados_sim, erro_sim = consultar_simulacao(identificador, data_analise)
    with st.container():
        c1, c2, c3, c4 = st.columns(4)
        if dados_sim:
            c1.metric("Clima", dados_sim.get('condicao_tempo', '--'))
            c2.metric("Irradiação", f"{dados_sim.get('irradiacao_solar_kwh_m2', 0)} kWh/m²")
            c3.metric("Temp. Máx", f"{dados_sim.get('temperatura_max_c', 0)}°C")
            c4.metric("Perda Térmica", f"{dados_sim.get('fator_perda_termica', 0)}%")
            impacto = str(dados_sim.get("impacto_na_rede", "NORMAL")).upper()
            if "CRITICO" in impacto or "ALTA" in impacto:
                st.error(f"🚨 Previsão de Impacto na Rede: {impacto}")
            else:
                st.success(f"✅ Previsão de Impacto na Rede: {impacto}")
        else:
            c1.metric("Clima", "--"); c2.metric("Irradiação", "--")
            c3.metric("Temp. Máx", "--"); c4.metric("Perda Térmica", "--")
            st.warning(f"⚠️ VPP Offline ou erro na API (Porta 8000). Detalhe: {erro_sim}")

    st.divider()

    st.header("🧠 Análise Preditiva (AI Duck Curve)")

    dna_atual = dados_gd.get("dna_perfil", {})
    fator_res = limpar_float(dna_atual.get('residencial', 0))
    fator_com = limpar_float(dna_atual.get('comercial', 0))
    fator_ind = limpar_float(dna_atual.get('industrial', 0))
    fator_rur = limpar_float(dna_atual.get('rural', 0))

    if dna_atual:
        def fmt_pct(val): return f"{limpar_float(val)*100:.0f}%"
        txt_res = fmt_pct(fator_res); txt_com = fmt_pct(fator_com)
        txt_ind = fmt_pct(fator_ind); txt_rur = fmt_pct(fator_rur)
        st.info(f"🧬 **Perfil de Carga (DNA):** Residencial: {txt_res} | Comercial: {txt_com} | Industrial: {txt_ind} | Rural: {txt_rur}")

    with st.spinner(f"IA processando fluxo de carga para {subestacao_obj.get('nome', 'Subestação')}..."):

        # 1. Potência GD
        potencia_kw = limpar_float(dados_gd.get("potencia_total_kw", 0))

        # 2. Consumo Mensal (mantive sua lógica)
        mes_int = data_analise.month
        dict_consumo = dados_gd.get("consumo_mensal", {})
        val = dict_consumo.get(mes_int) or dict_consumo.get(str(mes_int)) or dict_consumo.get(f"{mes_int:02d}")
        consumo_mes_atual = 0.0
        if val and limpar_float(val) > 0:
            consumo_mes_atual = limpar_float(val)
        else:
            valores_validos = [limpar_float(v) for k, v in dict_consumo.items() if limpar_float(v) > 0]
            if valores_validos:
                consumo_mes_atual = sum(valores_validos) / len(valores_validos)
            else:
                consumo_mes_atual = limpar_float(dados_gd.get("consumo_mensal_referencia", 0))
        if consumo_mes_atual <= 0:
            consumo_mes_atual = 1000.0
        if consumo_mes_atual < 500:
            consumo_mes_atual = consumo_mes_atual * 1000

        # 3. Coordenadas
        lat = float(subestacao_obj.get("latitude") or -15.7975)
        lon = float(subestacao_obj.get("longitude") or -47.8919)

        # 4. Payload e 5. Consulta IA
        payload_duck = {
            "data_alvo": data_analise.strftime("%Y-%m-%d"),
            "potencia_gd_kw": float(potencia_kw),
            "consumo_mes_alvo_mwh": float(consumo_mes_atual),
            "lat": lat, "lon": lon, "dna_perfil": dna_atual
        }
        res_ia, erro_ia = consultar_ia_predict(payload_duck)

        if res_ia:
            if 'timeline' in res_ia and 'consumo_kwh' in res_ia:

                analise_texto = res_ia.get('analise', 'Análise processada.')
                is_alerta = res_ia.get('alerta', False)
                if is_alerta:
                    st.error(f"**ALERTA DA IA:** {analise_texto}", icon="⚠️")
                else:
                    st.success(f"**DIAGNÓSTICO:** {analise_texto}", icon="✅")

                # CONTROLES DE VISUALIZAÇÃO
                st.markdown("##### 🕵️ Detalhar Consumo por Classe")
                col_f1, col_f2, col_f3 = st.columns(3)
                padrao_res = True if dna_atual and fator_res > 0.4 else False
                padrao_ind = True if dna_atual and fator_ind > 0.4 else False
                ver_res = col_f1.checkbox("🏠 Residencial", value=padrao_res)
                ver_com = col_f2.checkbox("🏢 Comercial", value=False)
                ver_ind = col_f3.checkbox("🏭 Industrial", value=padrao_ind)

                st.markdown("**Opções de exibição**")
                gen_y2 = st.checkbox("📈 Mostrar geração em eixo secundário (y2)", value=True)
                classes_em_graf_separado = st.checkbox("📊 Mostrar classes em gráfico separado (demanda absoluta kW)", value=False)

            
                timeline = res_ia.get('timeline', [f"{h:02d}:00" for h in range(24)])
                consumo_data = np.array(res_ia.get('consumo_kwh', [0]*24), dtype=float)
                geracao = np.array(res_ia.get('geracao_kwh', [0]*24), dtype=float)
                liquida = np.array(res_ia.get('carga_liquida_kwh', [0]*24), dtype=float)

             
                def array_ok(arr):
                    try:
                        a = np.array(arr, dtype=float)
                        return a.size == 24 and a.sum() > 0.0
                    except:
                        return False

               
                uso_backend_res = array_ok(res_ia.get('consumo_res_kwh'))
                uso_backend_com = array_ok(res_ia.get('consumo_com_kwh'))
                uso_backend_ind = array_ok(res_ia.get('consumo_ind_kwh'))

                consumo_res = np.array(res_ia.get('consumo_res_kwh'), dtype=float) if uso_backend_res else None
                consumo_com = np.array(res_ia.get('consumo_com_kwh'), dtype=float) if uso_backend_com else None
                consumo_ind = np.array(res_ia.get('consumo_ind_kwh'), dtype=float) if uso_backend_ind else None

                fonte_res = "backend_array" if uso_backend_res else None
                fonte_com = "backend_array" if uso_backend_com else None
                fonte_ind = "backend_array" if uso_backend_ind else None

                # Se backend não ofereceu arrays, busca dna normalizado: preferência por dna_perfil_usado do res_ia
                dna_backend = res_ia.get('dna_perfil_usado') or res_ia.get('dna_perfil') or None
                if dna_backend:
                    try:
                        dna_res_b = float(dna_backend.get('residencial', 0))
                        dna_com_b = float(dna_backend.get('comercial', 0))
                        dna_ind_b = float(dna_backend.get('industrial', 0))
                    except:
                        dna_res_b, dna_com_b, dna_ind_b = 0.0, 0.0, 0.0
                else:
                    dna_res_b, dna_com_b, dna_ind_b = 0.0, 0.0, 0.0

                # fallback dna vindo do dados_gd (front)
                dna_front = dados_gd.get('dna_perfil', {}) or {}
                try:
                    dna_res_f = float(dna_front.get('residencial', 0))
                    dna_com_f = float(dna_front.get('comercial', 0))
                    dna_ind_f = float(dna_front.get('industrial', 0))
                except:
                    dna_res_f, dna_com_f, dna_ind_f = 0.0, 0.0, 0.0

                # pick final factor: prioridade dna_backend > dna_front > default
                def pick_factor(b, f, default):
                    return b if (b is not None and b > 0) else (f if (f is not None and f > 0) else default)

                f_res = pick_factor(dna_res_b, dna_res_f, 0.4)
                f_com = pick_factor(dna_com_b, dna_com_f, 0.3)
                f_ind = pick_factor(dna_ind_b, dna_ind_f, 0.3)

                # normalizar soma para 1.0
                soma = f_res + f_com + f_ind
                if soma <= 0:
                    f_res, f_com, f_ind = 0.4, 0.3, 0.3
                    soma = 1.0
                f_res, f_com, f_ind = f_res / soma, f_com / soma, f_ind / soma

                # Se backend devolveu classes válidas, usa-as; senão cria curvas com comportamento horário distinto
                if consumo_res is None or consumo_com is None or consumo_ind is None:
                    # --- Gerar shapes horários típicos para cada classe (não todos iguais)
                    horas = np.arange(24)

                    # residencial: picos manhã (7-9) e noite (18-22)
                    res_shape = (
                        0.3 * np.exp(-((horas - 8) ** 2) / (2 * 2.0 ** 2)) +   # manhã
                        0.5 * np.exp(-((horas - 20) ** 2) / (2 * 2.0 ** 2)) +  # noite
                        0.2 * 0.2                                             # base noturna bem baixa
                    )
                    # comercial: pico durante horário comercial (9-17) com máximo perto de 13h
                    com_shape = (
                        1.0 * np.exp(-((horas - 13) ** 2) / (2 * 3.0 ** 2)) +  # dia
                        0.05                                                  # base baixa fora do horário
                    )
                    # industrial: relativamente constante, leve redução fim de semana/ noite (aqui só forma horária)
                    ind_shape = 0.8 + 0.2 * np.sin((horas / 24.0) * 2 * np.pi)  # pequena oscilação

                    # garantir não-negatividade
                    res_shape = np.clip(res_shape, 0.0001, None)
                    com_shape = np.clip(com_shape, 0.0001, None)
                    ind_shape = np.clip(ind_shape, 0.0001, None)

                    # normalizar shapes para soma 1 (cada um)
                    res_shape = res_shape / res_shape.sum()
                    com_shape = com_shape / com_shape.sum()
                    ind_shape = ind_shape / ind_shape.sum()

                    # agora pesa por fatores f_res,f_com,f_ind (importante para refletir mix total)
                    weighted_res = res_shape * f_res
                    weighted_com = com_shape * f_com
                    weighted_ind = ind_shape * f_ind

                    denom = (weighted_res + weighted_com + weighted_ind)
                    # evitar divisão por zero
                    denom[denom == 0] = 1.0

                    # proporção hora a hora que cada classe representa do consumo total
                    p_res = weighted_res / denom
                    p_com = weighted_com / denom
                    p_ind = weighted_ind / denom

                    # finalmente, curvas de classe: repartem o consumo_data horária
                    consumo_res = consumo_data * p_res
                    consumo_com = consumo_data * p_com
                    consumo_ind = consumo_data * p_ind

                    fonte_res = f"calculado (f_res={f_res:.3f})"
                    fonte_com = f"calculado (f_com={f_com:.3f})"
                    fonte_ind = f"calculado (f_ind={f_ind:.3f})"

                # Exibir fontes / fatores utilizados (ajuda no debug e confirmações)
                st.caption(f"Fontes das curvas por classe — Residencial: {fonte_res} | Comercial: {fonte_com} | Industrial: {fonte_ind}")
                st.caption(f"Fatores usados (res, com, ind): {f_res:.3f}, {f_com:.3f}, {f_ind:.3f}")

                # ### CONFIGURAÇÃO VISUAL: Curvas mais nítidas e grossas
                # Opacidades fixas em 1.0 para linhas (fill pode ser translúcido)
                opacity_total = 1.0
                opacity_class = 1.0
                opacity_ger = 1.0

                line_width_total = 5 
                line_width_class = 3  
                line_width_ger = 4

                # --- FIGURA PRINCIPAL (consumo + líquida + geração possivelmente em y2)
                fig_duck = go.Figure()
                visible_values_for_primary = []

                # Cores explícitas
                total_color = "rgb(0,86,179)"
                res_color   = "rgb(0,150,136)"
                com_color   = "rgb(156,39,176)"
                ind_color   = "rgb(244,67,54)"
                liq_color   = "rgb(103,58,183)"
                ger_color   = "rgb(255,152,0)"

                # Consumo Total (sempre plotado) - destaque relativo, mas com fill suave
                fig_duck.add_trace(go.Scatter(
                    x=timeline, y=consumo_data, name="Carga Total",
                    fill='tozeroy', mode='lines',
                    line=dict(color=total_color, width=line_width_total),
                    fillcolor='rgba(0,86,179,0.15)',
                    opacity=opacity_total,
                    hovertemplate='<b>Carga Total</b><br>%{x}<br>%{y:.1f} kW<extra></extra>'
                ))
                visible_values_for_primary.extend(consumo_data.tolist())

                # Classes — adiciona ao gráfico principal APENAS se o usuário selecionar.
                if ver_res and consumo_res is not None:
                    fig_duck.add_trace(go.Scatter(
                        x=timeline, y=consumo_res, name="Residencial", mode='lines',
                        line=dict(color=res_color, width=line_width_class, dash='dot'),
                        opacity=opacity_class,
                        hovertemplate='<b>Residencial</b>: %{y:.1f} kW<extra></extra>'
                    ))
                    visible_values_for_primary.extend(consumo_res.tolist())

                if ver_com and consumo_com is not None:
                    fig_duck.add_trace(go.Scatter(
                        x=timeline, y=consumo_com, name="Comercial", mode='lines',
                        line=dict(color=com_color, width=line_width_class, dash='dot'),
                        opacity=opacity_class,
                        hovertemplate='<b>Comercial</b>: %{y:.1f} kW<extra></extra>'
                    ))
                    visible_values_for_primary.extend(consumo_com.tolist())

                if ver_ind and consumo_ind is not None:
                    fig_duck.add_trace(go.Scatter(
                        x=timeline, y=consumo_ind, name="Industrial", mode='lines',
                        line=dict(color=ind_color, width=line_width_class, dash='dot'),
                        opacity=opacity_class,
                        hovertemplate='<b>Industrial</b>: %{y:.1f} kW<extra></extra>'
                    ))
                    visible_values_for_primary.extend(consumo_ind.tolist())

                # Carga líquida (plotamos no eixo principal) - mais grossa e nítida
                fig_duck.add_trace(go.Scatter(
                    x=timeline, y=liquida, name="Carga Líquida (Saldo)", mode='lines',
                    line=dict(color=liq_color, width=3, dash='longdash'),
                    opacity=1.0,
                    hovertemplate='<b>Carga Líquida</b>: %{y:.1f} kW<extra></extra>'
                ))
                visible_values_for_primary.extend(liquida.tolist())

                # Geração: se gen_y2 True, plota no eixo secundário 'y2' (não influencia escala principal)
                if gen_y2:
                    fig_duck.add_trace(go.Scatter(
                        x=timeline, y=geracao, name="Geração Solar", mode='lines',
                        line=dict(color=ger_color, width=line_width_ger),
                        yaxis='y2',
                        opacity=opacity_ger,
                        hovertemplate='<b>Geração</b>: %{y:.1f} kW<extra></extra>'
                    ))
                else:
                    fig_duck.add_trace(go.Scatter(
                        x=timeline, y=geracao, name="Geração Solar", mode='lines',
                        line=dict(color=ger_color, width=line_width_ger),
                        opacity=opacity_ger,
                        hovertemplate='<b>Geração</b>: %{y:.1f} kW<extra></extra>'
                    ))
                    visible_values_for_primary.extend(geracao.tolist())

                # Linha zero
                fig_duck.add_hline(y=0, line_dash="solid", line_width=2, line_color="rgba(220,53,69,1.0)", annotation_text="Limiar Inversão")

                # --- CALCULAR RANGE DO EIXO PRINCIPAL com base apenas nas séries visíveis naquele eixo
                if visible_values_for_primary:
                    v_min = float(np.min(visible_values_for_primary))
                    v_max = float(np.max(visible_values_for_primary))
                    margem = (v_max - v_min) * 0.10 if (v_max - v_min) != 0 else max(1.0, v_max * 0.1)
                    y_max = v_max + abs(margem)
                    y_min = (v_min - abs(margem)) if v_min < 0 else 0.0
                else:
                    y_min, y_max = 0.0, 1000.0

                # --- LAYOUT (inclui y2 se necessário)
                layout_kwargs = dict(
                    height=550,
                    title=dict(text=f"Curva de Carga - {subestacao_obj.get('nome', 'Subestação')}", font=dict(size=18, color="#efefef")),
                    yaxis_title="Consumo Elétrico Horário (kW)",
                    xaxis_title="Hora do Dia",
                    plot_bgcolor='rgba(0,0,0,0)',
                    paper_bgcolor='rgba(0,0,0,0)',
                    font=dict(color="#efefef"),
                    xaxis=dict(showgrid=True, gridcolor="rgba(200,200,200,0.25)", zeroline=False),
                    yaxis=dict(range=[y_min, y_max], showgrid=True, gridcolor="rgba(200,200,200,0.25)", zeroline=True, zerolinewidth=1, zerolinecolor="rgba(150,150,150,0.35)"),
                    hovermode="x unified",
                    legend=dict(orientation="h", y=1.12, x=0.5, xanchor='center', bgcolor='rgba(255,255,255,0.6)', bordercolor='rgba(0,0,0,0.08)', borderwidth=1, font=dict(color='#efefef')),
                    margin=dict(l=40, r=60 if gen_y2 else 40, t=100, b=40)
                )
                if gen_y2:
                    # define yaxis2 (overlay y on right)
                    layout_kwargs['yaxis2'] = dict(title="Geração (kW)", overlaying='y', side='right', showgrid=False)

                fig_duck.update_layout(**layout_kwargs)
                st.plotly_chart(fig_duck, use_container_width=True)

                # --- GRÁFICO SEPARADO (OPCIONAL) PARA CLASSES EM DEMANDA ABSOLUTA (kW)
                if classes_em_graf_separado and (ver_res or ver_com or ver_ind):
                    fig_classes = go.Figure()
                    if ver_res:
                        fig_classes.add_trace(go.Scatter(x=timeline, y=consumo_res, name="Residencial (kW)", mode='lines', line=dict(color=res_color, width=2.5), opacity=0.95, hovertemplate='<b>Residencial</b>: %{y:.1f} kW<extra></extra>'))
                    if ver_com:
                        fig_classes.add_trace(go.Scatter(x=timeline, y=consumo_com, name="Comercial (kW)", mode='lines', line=dict(color=com_color, width=2.5), opacity=0.95, hovertemplate='<b>Comercial</b>: %{y:.1f} kW<extra></extra>'))
                    if ver_ind:
                        fig_classes.add_trace(go.Scatter(x=timeline, y=consumo_ind, name="Industrial (kW)", mode='lines', line=dict(color=ind_color, width=2.5), opacity=0.95, hovertemplate='<b>Industrial</b>: %{y:.1f} kW<extra></extra>'))

                    fig_classes.update_layout(
                        height=320,
                        title=dict(text="Curvas por Classe (demanda absoluta, kW)", font=dict(size=16)),
                        yaxis_title="Potência (kW)",
                        xaxis_title="Hora do Dia",
                        plot_bgcolor='rgba(0,0,0,0)',
                        paper_bgcolor='rgba(0,0,0,0)',
                        hovermode="x unified",
                        margin=dict(l=40, r=40, t=60, b=40),
                        legend=dict(orientation="h", y=1.12, x=0.5, xanchor='center')
                    )
                    st.plotly_chart(fig_classes, use_container_width=True)

                # --- KPIs ---
                st.markdown("---")
                kp1, kp2, kp3 = st.columns(3)
                val_liquida_min = float(liquida.min()) if liquida.size else 0.0
                val_geracao_max = float(geracao.max()) if geracao.size else 0.0
                kp1.metric("Pico de Geração Solar", f"{val_geracao_max:,.2f} kW")
                delta_lbl = "Risco Inversão" if val_liquida_min < 0 else "Operação Segura"
                kp2.metric("Mínima Carga Líquida", f"{val_liquida_min:,.2f} kW", delta=delta_lbl, delta_color="inverse")
                kp3.metric("Consumo Mensal Ref.", f"{consumo_mes_atual:,.0f} kWh")

            else:
                st.error("O Backend retornou dados incompletos.")
        else:
            st.warning(f"Não foi possível obter a previsão da IA: {erro_ia}")
