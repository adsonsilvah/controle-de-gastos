import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime
import io
import os

import importlib
import database
import analytics
importlib.reload(database)
importlib.reload(analytics)
from parsers import scan_and_ingest_all

# 1. Configuração da Página
st.set_page_config(
    page_title="Gestão Financeira Pessoal",
    page_icon="💰",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Estilização CSS Moderna
st.markdown("""
<style>
    .metric-card {
        background: #ffffff;
        border-radius: 12px;
        padding: 18px;
        box-shadow: 0 2px 10px rgba(0,0,0,0.06);
        border: 1px solid #e9ecef;
        margin-bottom: 15px;
    }
    .stTabs [data-baseweb="tab-list"] {
        gap: 6px;
    }
    .stTabs [data-baseweb="tab"] {
        padding: 10px 16px;
        border-radius: 8px;
        font-weight: 600;
    }
</style>
""", unsafe_allow_html=True)

ALL_CATEGORIES = [
    "Supermercado & Feira",
    "Alimentação & Restaurante",
    "Transporte & Combustível",
    "E-commerce & Compras",
    "Moradia & Contas",
    "Educação",
    "Lazer & Bem-Estar",
    "Saúde & Farmácia",
    "Casa & Construção",
    "Serviços & Recargas",
    "Impostos & INSS (Folha)",
    "Tarifas & Encargos",
    "Transferência / Fatura",
    "Salário & Proventos",
    "Benefícios (VA / VT)",
    "Rendimentos & Investimentos",
    "Estornos & Devoluções",
    "Outras Receitas",
    "Outros Gastos"
]

def fmt_brl(val: float) -> str:
    return f"R$ {val:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

# 2. Inicialização do Banco
database.init_db()

def get_db_mtime() -> float:
    return os.path.getmtime(database.DB_PATH) if os.path.exists(database.DB_PATH) else 0.0

@st.cache_data(ttl=60)
def load_data(mtime: float = 0.0):
    raw_data = database.get_all_transactions()
    if not raw_data:
        return pd.DataFrame()
    df = pd.DataFrame(raw_data)
    df["data_dt"] = pd.to_datetime(df["data"])
    df["mes_ano"] = df["data_dt"].dt.strftime("%Y-%m")
    df["dia"] = df["data_dt"].dt.strftime("%d")
    return df

@st.cache_data(ttl=60)
def load_contracheques(mtime: float = 0.0):
    rows = database.get_all_contracheques()
    if not rows:
        return pd.DataFrame()
    return pd.DataFrame(rows)

# 3. Barra Lateral (Sidebar)
with st.sidebar:
    st.title("💰 Finanças")
    st.caption("Organizador, Previsões e Planejamento")
    
    st.markdown("---")
    
    if st.button("🔄 Sincronizar Pasta dados/", width="stretch", help="Lê novos extratos e demonstrativos de pagamento da pasta dados/"):
        with st.spinner("Sincronizando arquivos e benefícios..."):
            rep = scan_and_ingest_all("dados")
            st.cache_data.clear()
            st.success(f"Sincronizado! {rep['transacoes_inseridas']} novas transações.")
            st.rerun()

    # Upload Direto pela Interface
    st.subheader("📥 Adicionar Arquivo")
    uploaded_file = st.file_uploader(
        "Arraste extrato, fatura ou contracheque (PDF/CSV)",
        type=["pdf", "csv"],
        help="O arquivo será salvo na pasta dados/ correspondente e processado."
    )
    
    if uploaded_file is not None:
        banco_destino = st.selectbox(
            "Selecione a Pasta / Origem:",
            ["inter", "salario", "banco do brasil", "nubank", "atacadao", "caixa", "mercado pago", "boletos", "outro"]
        )
        if st.button("Processar Arquivo", width="stretch"):
            with st.spinner("Salvando e processando..."):
                target_dir = os.path.join("dados", banco_destino)
                os.makedirs(target_dir, exist_ok=True)
                dest_path = os.path.join(target_dir, uploaded_file.name)
                
                with open(dest_path, "wb") as f:
                    f.write(uploaded_file.getbuffer())
                    
                scan_and_ingest_all("dados")
                st.cache_data.clear()
                st.success("Arquivo importado com sucesso!")
                st.rerun()

    st.markdown("---")
    st.subheader("🔍 Filtros")
    
    df_all = load_data(get_db_mtime())
    
    if not df_all.empty:
        meses_disponiveis = sorted(df_all["mes_ano"].unique(), reverse=True)
        mes_selecionado = st.selectbox("Período (Mês/Ano)", ["Todos"] + list(meses_disponiveis))
        
        bancos_disponiveis = sorted(df_all["banco"].unique())
        bancos_selecionados = st.multiselect("Origem / Instituição", bancos_disponiveis, default=bancos_disponiveis)
        
        tipos_conta = sorted(df_all["conta_tipo"].unique())
        tipos_conta_selecionados = st.multiselect("Tipo de Conta", tipos_conta, default=tipos_conta)
        
        ignorar_transferencias = st.checkbox(
            "Ocultar Transferências / Repasses",
            value=True,
            help="Evita duplicar pagamentos de fatura, transferências entre contas próprias e repasses da conta salário."
        )
        incluir_inss_despesas = st.checkbox(
            "Incluir INSS Retido em Folha nas Despesas",
            value=True,
            help="Quando marcado, mostra o desconto de INSS do contracheque no gráfico de despesas (junto com Salário Bruto nas receitas)."
        )
    else:
        mes_selecionado = "Todos"
        bancos_selecionados = []
        tipos_conta_selecionados = []
        ignorar_transferencias = True
        incluir_inss_despesas = True

# 4. Processamento dos Filtros
df_filtered = df_all.copy()

if not df_filtered.empty:
    if mes_selecionado != "Todos":
        df_filtered = df_filtered[df_filtered["mes_ano"] == mes_selecionado]
    if bancos_selecionados:
        df_filtered = df_filtered[df_filtered["banco"].isin(bancos_selecionados)]
    if tipos_conta_selecionados:
        df_filtered = df_filtered[df_filtered["conta_tipo"].isin(tipos_conta_selecionados)]
    if not incluir_inss_despesas:
        df_filtered = df_filtered[df_filtered["categoria"] != "Impostos & INSS (Folha)"]
    if ignorar_transferencias:
        df_calculos = df_filtered[df_filtered["tipo_movimentacao"].isin(["Despesa", "Receita"])]
    else:
        df_calculos = df_filtered.copy()
else:
    df_calculos = pd.DataFrame()

# 5. Interface Principal com Abas
(
    tab_overview,
    tab_previsao,
    tab_planejamento,
    tab_cartoes,
    tab_salario,
    tab_extrato,
    tab_regras,
    tab_arquivos
) = st.tabs([
    "📊 Visão Geral",
    "🔮 Previsão vs Realizado",
    "🎯 Divisão do Salário",
    "💳 Cartões & Gastos Fixos",
    "💼 Salário, VA/VT & FGTS",
    "📋 Extrato Consolidado",
    "🏷️ Categorias & Regras",
    "📁 Arquivos & Config"
])

# ==========================================================
# ABA 1: VISÃO GERAL & GRÁFICOS
# ==========================================================
with tab_overview:
    if df_filtered.empty:
        st.info("Nenhuma transação encontrada. Clique em 'Sincronizar' na barra lateral.")
    else:
        total_despesas = df_calculos[df_calculos["tipo_movimentacao"] == "Despesa"]["valor"].sum()
        total_receitas = df_calculos[df_calculos["tipo_movimentacao"] == "Receita"]["valor"].sum()
        saldo_liquido = total_receitas - total_despesas
        
        cartoes_mask = (df_filtered["conta_tipo"] == "Cartão de Crédito") & (df_filtered["tipo_movimentacao"] == "Despesa")
        total_cartoes = df_filtered[cartoes_mask]["valor"].sum()

        c1, c2, c3, c4 = st.columns(4)
        with c1:
            st.metric("💸 Total de Despesas", fmt_brl(total_despesas))
        with c2:
            st.metric("💰 Total de Receitas (Salário + VA/VT + Outras)", fmt_brl(total_receitas))
        with c3:
            st.metric("⚖️ Saldo Líquido do Período", fmt_brl(saldo_liquido), delta=fmt_brl(saldo_liquido))
        with c4:
            st.metric("💳 Gastos em Cartões de Crédito", fmt_brl(total_cartoes))

        st.markdown("<br>", unsafe_allow_html=True)
        
        col_g1, col_g2 = st.columns([1, 1])
        
        with col_g1:
            st.subheader("🍩 Com o que foi gasto (Despesas por Categoria)")
            df_cat = df_calculos[df_calculos["tipo_movimentacao"] == "Despesa"]
            if not df_cat.empty:
                cat_summary = df_cat.groupby("categoria")["valor"].sum().reset_index().sort_values(by="valor", ascending=False)
                fig_pie = px.pie(
                    cat_summary,
                    values="valor",
                    names="categoria",
                    hole=0.45,
                    color_discrete_sequence=px.colors.qualitative.Prism
                )
                fig_pie.update_traces(
                    textposition="inside",
                    textinfo="percent+label",
                    hovertemplate="<b>%{label}</b><br>R$ %{value:,.2f}<br>%{percent}"
                )
                fig_pie.update_layout(showlegend=False, margin=dict(t=10, b=10, l=10, r=10), height=370)
                st.plotly_chart(fig_pie, width="stretch")
            else:
                st.caption("Sem despesas registradas no período selecionado.")

        with col_g2:
            st.subheader("📅 Evolução Mensal (Receitas vs Despesas)")
            df_mes = df_all[df_all["tipo_movimentacao"].isin(["Despesa", "Receita"])]
            if not incluir_inss_despesas:
                df_mes = df_mes[df_mes["categoria"] != "Impostos & INSS (Folha)"]
            if not df_mes.empty:
                mensal_agg = df_mes.groupby(["mes_ano", "tipo_movimentacao"])["valor"].sum().reset_index()
                fig_bar = px.bar(
                    mensal_agg,
                    x="mes_ano",
                    y="valor",
                    color="tipo_movimentacao",
                    barmode="group",
                    text_auto=".2f",
                    color_discrete_map={"Despesa": "#e63946", "Receita": "#2a9d8f"},
                    labels={"mes_ano": "Mês/Ano", "valor": "Total (R$)", "tipo_movimentacao": "Tipo"}
                )
                fig_bar.update_layout(margin=dict(t=10, b=10, l=10, r=10), height=370, legend=dict(orientation="h", y=1.1))
                st.plotly_chart(fig_bar, width="stretch")

        col_g3, col_g4 = st.columns([1, 1])
        
        with col_g3:
            st.subheader("🏦 Gastos por Origem (Bancos, Cartões e Benefícios)")
            df_banco = df_calculos[df_calculos["tipo_movimentacao"] == "Despesa"]
            if not df_banco.empty:
                banco_agg = df_banco.groupby("banco")["valor"].sum().reset_index().sort_values(by="valor", ascending=True)
                fig_banco = px.bar(
                    banco_agg,
                    x="valor",
                    y="banco",
                    orientation="h",
                    color="banco",
                    text_auto=".2f",
                    color_discrete_sequence=px.colors.qualitative.Safe,
                    labels={"valor": "Total Gasto (R$)", "banco": "Origem"}
                )
                fig_banco.update_layout(showlegend=False, margin=dict(t=10, b=10, l=10, r=10), height=340)
                st.plotly_chart(fig_banco, width="stretch")
                
        with col_g4:
            st.subheader("📊 Resumo de Gastos por Categoria")
            if not df_cat.empty:
                cat_table = df_cat.groupby("categoria").agg(
                    Qtd=("valor", "count"),
                    Total=("valor", "sum")
                ).reset_index().sort_values(by="Total", ascending=False)
                cat_table["% do Total"] = (cat_table["Total"] / cat_table["Total"].sum() * 100).round(1).astype(str) + "%"
                st.dataframe(
                    cat_table.rename(columns={"categoria": "Categoria", "Qtd": "Transações", "Total": "Total Gasto (R$)"}).style.format({"Total Gasto (R$)": "R$ {:,.2f}"}),
                    hide_index=True,
                    width="stretch",
                    height=340
                )

# ==========================================================
# ABA 2: PREVISÃO DE GASTOS VS REALIZADO
# ==========================================================
with tab_previsao:
    st.subheader("🔮 Previsão de Gastos para os Próximos Meses & Comparativo Previsto vs Realizado")
    st.caption(
        "Projeta os gastos dos próximos meses somando **Gastos Fixos/Assinaturas + Parcelas de Cartão já contratadas + "
        "VA/VT + Média de Gastos Variáveis**, e compara o **Valor Previsto** com o **Gasto Realizado** assim que o mês chega."
    )

    custom_forecasts = database.get_custom_forecasts()
    custom_fixed = database.get_custom_fixed_expenses()
    df_forecast, fc_info = analytics.build_forecast_and_comparison(
        df_all,
        custom_forecasts=custom_forecasts,
        custom_fixed=custom_fixed,
        include_inss=incluir_inss_despesas
    )

    if not df_forecast.empty:
        # Seletor de mês para inspecionar o comparativo em destaque
        meses_fc = df_forecast["Mês/Ano"].tolist()
        default_idx = meses_fc.index("2026-10") if "2026-10" in meses_fc else 0
        col_sel_m, col_meta_form = st.columns([1, 2])

        with col_sel_m:
            mes_foco = st.selectbox("📅 Selecione o Mês para Analisar em Detalhe:", meses_fc, index=default_idx)
            row_foco = df_forecast[df_forecast["Mês/Ano"] == mes_foco].iloc[0]

        with col_meta_form:
            with st.expander("🎯 Definir / Ajustar Meta ou Previsão Manual para um Mês (ex: Janeiro/2027)", expanded=False):
                f_c1, f_c2, f_c3 = st.columns([1, 1, 1])
                with f_c1:
                    mes_meta_input = st.selectbox("Mês/Ano:", meses_fc, index=meses_fc.index(mes_foco), key="meta_mes_sel")
                with f_c2:
                    val_default = float(df_forecast[df_forecast["Mês/Ano"] == mes_meta_input]["Previsto / Meta Total (R$)"].iloc[0])
                    val_meta_input = st.number_input("Valor Previsto para o Mês (R$):", min_value=0.0, value=val_default, step=100.0)
                with f_c3:
                    obs_meta_input = st.text_input("Observação (opcional):", placeholder="Ex: Meta Janeiro")
                b_m1, b_m2 = st.columns([1, 1])
                with b_m1:
                    if st.button("💾 Salvar Previsão Manual para o Mês", width="stretch"):
                        database.set_custom_forecast(mes_meta_input, val_meta_input, obs_meta_input)
                        st.success(f"Previsão de {fmt_brl(val_meta_input)} salva para {mes_meta_input}!")
                        st.rerun()
                with b_m2:
                    if st.button("🔄 Restaurar Cálculo Automático do Mês", width="stretch"):
                        database.delete_custom_forecast(mes_meta_input)
                        st.success(f"Cálculo automático restaurado para {mes_meta_input}!")
                        st.rerun()

        # Cards de Destaque do Mês Selecionado (Exemplo: Previsto 10k vs Gasto 9k -> Diferença 1k)
        prev_val = float(row_foco["Previsto / Meta Total (R$)"])
        real_val = float(row_foco["Gasto Realizado (R$)"])
        dif_val = float(row_foco["Diferença (Previsto - Realizado)"])
        parc_val = float(row_foco["Parcelas de Cartão no Mês (R$)"])

        kc1, kc2, kc3, kc4 = st.columns(4)
        with kc1:
            st.metric(f"🎯 Previsão Total ({mes_foco})", fmt_brl(prev_val), help=row_foco["Origem da Previsão"])
        with kc2:
            st.metric(f"💸 Gasto Realizado ({mes_foco})", fmt_brl(real_val))
        with kc3:
            label_dif = "✅ Economia (Previsto - Gasto)" if dif_val >= 0 else "⚠️ Acima do Previsto"
            st.metric(
                label_dif,
                fmt_brl(abs(dif_val)),
                delta=f"{fmt_brl(dif_val)} vs previsto",
                delta_color="normal"
            )
        with kc4:
            st.metric(f"💳 Parcelas Contratadas ({mes_foco})", fmt_brl(parc_val))

        # Gráfico Comparativo Previsto vs Realizado
        st.markdown("#### 📊 Gráfico Comparativo: Previsto vs Realizado (Histórico + Próximos 6 Meses)")
        fig_fc = go.Figure()
        fig_fc.add_trace(go.Bar(
            x=df_forecast["Mês/Ano"],
            y=df_forecast["Previsto / Meta Total (R$)"],
            name="Previsto / Meta (R$)",
            marker_color="#457b9d",
            text=df_forecast["Previsto / Meta Total (R$)"].apply(lambda v: f"R$ {v:,.0f}"),
            textposition="auto"
        ))
        fig_fc.add_trace(go.Bar(
            x=df_forecast["Mês/Ano"],
            y=df_forecast["Gasto Realizado (R$)"],
            name="Gasto Realizado (R$)",
            marker_color="#e63946",
            text=df_forecast["Gasto Realizado (R$)"].apply(lambda v: f"R$ {v:,.0f}" if v > 0 else ""),
            textposition="auto"
        ))
        fig_fc.update_layout(
            barmode="group",
            height=380,
            margin=dict(t=20, b=20, l=20, r=20),
            legend=dict(orientation="h", y=1.12),
            xaxis_title="Mês / Ano",
            yaxis_title="Valor (R$)"
        )
        st.plotly_chart(fig_fc, width="stretch")

        # Tabela Detalhada Mês a Mês
        st.markdown("#### 📋 Tabela Detalhada de Projeção e Comparativo Mensal")
        st.dataframe(
            df_forecast.style.format({
                "Fixos + VA/VT + Folha (R$)": "R$ {:,.2f}",
                "Parcelas de Cartão no Mês (R$)": "R$ {:,.2f}",
                "Estimativa Variável (R$)": "R$ {:,.2f}",
                "Previsto / Meta Total (R$)": "R$ {:,.2f}",
                "Gasto Realizado (R$)": "R$ {:,.2f}",
                "Diferença (Previsto - Realizado)": "R$ {:+,.2f}"
            }),
            hide_index=True,
            width="stretch",
            height=390
        )

# ==========================================================
# ABA 3: DIVISÃO E ORGANIZAÇÃO DO SALÁRIO / RENDA
# ==========================================================
with tab_planejamento:
    st.subheader("🎯 Divisão e Organização dos Gastos Baseada na Renda (Salário Positivo)")
    st.caption(
        "Defina como seu salário líquido (ex: ~R$ 3.000) deve ser dividido entre **Contas Essenciais**, "
        "**Poupança/Reserva (Guardar)**, **Lazer** e **Compras**, escolhendo entre **Porcentagem (%)** ou **Valor Fixo (R$)**."
    )

    col_p1, col_p2, col_p3 = st.columns([1, 1, 1])
    with col_p1:
        meses_plan = sorted([m for m in df_all["mes_ano"].unique() if m >= "2026-08"], reverse=True) if not df_all.empty else ["2026-10"]
        default_m_plan = "2026-10" if "2026-10" in meses_plan else meses_plan[0]
        mes_plan_sel = st.selectbox("📅 Mês de Referência para Comparação:", meses_plan, index=meses_plan.index(default_m_plan))

    # Descobre salário líquido real do mês ou usa valor base configurável (~R$ 3.000)
    df_cc_plan = load_contracheques()
    sal_padrao = float(database.get_config("salario_base_planejamento", "3000.00").replace(",", "."))
    if not df_cc_plan.empty:
        cc_match = df_cc_plan[df_cc_plan["data_pagamento"].str.startswith(mes_plan_sel)]
        if not cc_match.empty:
            sal_padrao = float(cc_match.iloc[0]["salario_liquido"])

    with col_p2:
        renda_base_input = st.number_input(
            "💵 Renda Positiva / Salário Base para Divisão (R$):",
            min_value=100.0,
            value=sal_padrao,
            step=50.0,
            help="Valor líquido que entra no mês sobre o qual serão calculados os percentuais."
        )
    with col_p3:
        incluir_va_vt_na_divisao = st.checkbox(
            "Somar VA/VT (+R$ 710) na Renda Base da Divisão",
            value=False,
            help="Desmarcado = planeja apenas sobre o Salário Líquido (~R$ 3k). Marcado = soma também os R$ 710 de Vale-Alimentação e Transporte."
        )

    renda_efetiva = renda_base_input + (710.0 if incluir_va_vt_na_divisao else 0.0)
    regras_divisao = database.get_income_division()
    df_mes_plan = df_all[df_all["mes_ano"] == mes_plan_sel] if not df_all.empty else pd.DataFrame()

    df_resultado_div = analytics.calculate_income_division(
        df_mes_plan,
        renda_base=renda_efetiva,
        division_rules=regras_divisao,
        ignore_benefits_in_salary_split=(not incluir_va_vt_na_divisao)
    )

    # Editor rápido das regras de divisão (% ou R$)
    with st.expander("⚙️ Configurar Percentuais (%) ou Valores Inteiros (R$) de Cada Grupo", expanded=False):
        with st.form("form_divisao_renda"):
            st.markdown("Escolha para cada grupo se deseja definir em **Percentual (%)** do salário ou em **Valor Fixo (R$)**:")
            novos_valores = []
            for idx, r_div in enumerate(regras_divisao):
                c_d1, c_d2, c_d3 = st.columns([2, 1, 1])
                with c_d1:
                    st.markdown(f"**{r_div['grupo']}**")
                    st.caption(f"Categorias: {', '.join(r_div['categorias'])}")
                with c_d2:
                    modo_sel = st.selectbox(
                        "Modo",
                        ["Percentual (%)", "Valor Fixo (R$)"],
                        index=0 if "Percentual" in r_div["modo"] else 1,
                        key=f"modo_div_{idx}"
                    )
                with c_d3:
                    val_sel = st.number_input(
                        "Valor (% ou R$)",
                        min_value=0.0,
                        value=float(r_div["valor_config"]),
                        step=5.0 if "Percentual" in r_div["modo"] else 50.0,
                        key=f"val_div_{idx}"
                    )
                novos_valores.append((r_div["grupo"], modo_sel, val_sel))

            if st.form_submit_button("💾 Salvar Divisão do Salário", width="stretch"):
                for grp_name, m_s, v_s in novos_valores:
                    database.update_income_division(grp_name, m_s, v_s)
                database.set_config("salario_base_planejamento", f"{renda_base_input:.2f}")
                st.success("Divisão de renda atualizada com sucesso!")
                st.rerun()

    # Barras de Progresso Visuais e Cards de Alocação
    st.markdown(f"#### 📊 Painel de Alocação da Renda em **{mes_plan_sel}** (Base: **{fmt_brl(renda_efetiva)}**)")
    cols_bucket = st.columns(len(df_resultado_div))
    for i, (_, row_b) in enumerate(df_resultado_div.iterrows()):
        with cols_bucket[i]:
            ideal = float(row_b["Ideal / Planejado (R$)"])
            real = float(row_b["Realizado no Mês (R$)"])
            pct_uso = min(1.0, real / ideal) if ideal > 0 else 0.0
            st.metric(
                row_b["Grupo de Destino"],
                f"Meta: {fmt_brl(ideal)}",
                delta=f"Real: {fmt_brl(real)} ({row_b['% Real da Renda']})",
                delta_color="off"
            )
            st.progress(pct_uso)
            st.caption(row_b["Status"])

    # Gráfico Planejado vs Realizado por Grupo
    col_div_chart, col_div_table = st.columns([1, 1])
    with col_div_chart:
        st.markdown("##### 📈 Ideal Planejado vs Realizado por Grupo")
        fig_div = go.Figure()
        fig_div.add_trace(go.Bar(
            x=df_resultado_div["Grupo de Destino"],
            y=df_resultado_div["Ideal / Planejado (R$)"],
            name="Ideal / Planejado (R$)",
            marker_color="#2a9d8f",
            text=df_resultado_div["Ideal / Planejado (R$)"].apply(fmt_brl),
            textposition="auto"
        ))
        fig_div.add_trace(go.Bar(
            x=df_resultado_div["Grupo de Destino"],
            y=df_resultado_div["Realizado no Mês (R$)"],
            name="Realizado no Mês (R$)",
            marker_color="#e76f51",
            text=df_resultado_div["Realizado no Mês (R$)"].apply(fmt_brl),
            textposition="auto"
        ))
        fig_div.update_layout(barmode="group", height=350, margin=dict(t=10, b=10, l=10, r=10), legend=dict(orientation="h", y=1.12))
        st.plotly_chart(fig_div, width="stretch")

    with col_div_table:
        st.markdown("##### 📋 Tabela Resumo da Organização do Salário")
        st.dataframe(
            df_resultado_div[[
                "Grupo de Destino", "Regra Definida", "Ideal / Planejado (R$)",
                "Realizado no Mês (R$)", "Saldo / Diferença (R$)", "Status"
            ]].style.format({
                "Ideal / Planejado (R$)": "R$ {:,.2f}",
                "Realizado no Mês (R$)": "R$ {:,.2f}",
                "Saldo / Diferença (R$)": "R$ {:+,.2f}"
            }),
            hide_index=True,
            width="stretch",
            height=350
        )

# ==========================================================
# ABA 4: CARTÕES DE CRÉDITO, GASTOS FIXOS & ASSINATURAS
# ==========================================================
with tab_cartoes:
    st.subheader("💳 Gastos Fixos (Assinaturas/Mensalidades) e Compras Parceladas nos Cartões")
    
    custom_fixed_list = database.get_custom_fixed_expenses()
    df_fixed_exp = analytics.detect_fixed_expenses(df_all, custom_fixed_list)
    df_installments, monthly_comm_map = analytics.extract_installment_plans(df_all)

    # KPIs de Compromissos Fixos e Parcelamentos
    soma_fixos_mensal = float(df_fixed_exp["Valor Mensal Fixo (R$)"].sum()) if not df_fixed_exp.empty else 0.0
    parcelas_ativas_df = df_installments[df_installments["Status"].str.contains("Ativo")] if not df_installments.empty else pd.DataFrame()
    soma_parcelas_mensal = float(parcelas_ativas_df["Valor da Parcela (R$)"].sum()) if not parcelas_ativas_df.empty else 0.0
    saldo_devedor_parcelas = float(parcelas_ativas_df["Saldo Restante a Pagar (R$)"].sum()) if not parcelas_ativas_df.empty else 0.0

    ck1, ck2, ck3 = st.columns(3)
    with ck1:
        st.metric("🔁 Total de Assinaturas / Mensalidades Fixas", fmt_brl(soma_fixos_mensal) + " / mês")
    with ck2:
        st.metric("📦 Total de Parcelas Ativas no Cartão", fmt_brl(soma_parcelas_mensal) + " / mês")
    with ck3:
        st.metric("⏳ Saldo Restante de Parcelamentos Futuros", fmt_brl(saldo_devedor_parcelas))

    st.markdown("---")
    col_fix1, col_fix2 = st.columns([2, 1])

    with col_fix1:
        st.markdown("#### 🔁 Gastos Fixos, Assinaturas e Mensalidades Identificados")
        st.caption("Valores cobrados todos os meses com exatamente o mesmo valor (assinaturas, anuidades, pacotes de tarifas e planos).")
        if not df_fixed_exp.empty:
            st.dataframe(
                df_fixed_exp.style.format({"Valor Mensal Fixo (R$)": "R$ {:,.2f}"}),
                hide_index=True,
                width="stretch"
            )
        else:
            st.info("Nenhum gasto fixo recorrente identificado.")

    with col_fix2:
        st.markdown("#### ➕ Cadastrar Nova Assinatura / Gasto Fixo")
        with st.form("form_novo_fixo"):
            f_nome = st.text_input("Nome da Assinatura / Mensalidade:", placeholder="Ex: Netflix, Internet, Spotify")
            f_banco = st.selectbox("Cartão / Conta:", ["Banco Inter", "Nubank", "Cartão Atacadão", "Banco do Brasil", "Caixa Econômica", "Mercado Pago"])
            f_val = st.number_input("Valor Mensal Fixo (R$):", min_value=0.0, step=5.0)
            f_cat = st.selectbox("Categoria:", ALL_CATEGORIES, index=ALL_CATEGORIES.index("Serviços & Recargas"))
            if st.form_submit_button("Adicionar Gasto Fixo", width="stretch"):
                if f_nome.strip() and f_val > 0:
                    database.add_custom_fixed_expense(f_nome, f_banco, f_val, f_cat)
                    st.success(f"'{f_nome}' adicionado aos gastos fixos mensais!")
                    st.rerun()

        if custom_fixed_list:
            del_opts = {f"{x['nome']} (R$ {x['valor']:.2f})": x["id"] for x in custom_fixed_list}
            del_sel = st.selectbox("Remover gasto fixo manual:", list(del_opts.keys()))
            if st.button("🗑️ Remover Selecionado", width="stretch"):
                database.delete_custom_fixed_expense(del_opts[del_sel])
                st.rerun()

    st.markdown("---")
    st.markdown("#### 📦 Controle de Compras Parceladas nos Cartões (Ativas vs Quitadas)")
    st.caption("Acompanhe quantas parcelas faltam para cada compra nos cartões Nubank e Atacadão e quando cada compromisso termina.")
    if not df_installments.empty:
        st.dataframe(
            df_installments.style.format({
                "Valor da Parcela (R$)": "R$ {:,.2f}",
                "Saldo Restante a Pagar (R$)": "R$ {:,.2f}"
            }),
            hide_index=True,
            width="stretch"
        )

# ==========================================================
# ABA 5: SALÁRIO, BENEFÍCIOS (VA/VT) & FGTS
# ==========================================================
with tab_salario:
    st.subheader("💼 Demonstrativos de Pagamento (Salário), Vale-Alimentação, Vale-Transporte e FGTS")
    
    df_cc = load_contracheques()
    va_atual = float(database.get_config("vale_alimentacao_valor", "460.00").replace(",", "."))
    vt_atual = float(database.get_config("vale_transporte_valor", "250.00").replace(",", "."))
    benef_ativo = database.get_config("beneficios_ativos", "1") == "1"

    if not df_cc.empty:
        k1, k2, k3, k4 = st.columns(4)
        with k1:
            st.metric("💵 Salário Bruto Acumulado", fmt_brl(df_cc["salario_bruto"].sum()))
        with k2:
            st.metric("✅ Salário Líquido Acumulado", fmt_brl(df_cc["salario_liquido"].sum()))
        with k3:
            st.metric("🏦 FGTS Depositado (Contracheques)", fmt_brl(df_cc["fgts_deposito"].sum()))
        with k4:
            st.metric("🍱 Benefícios Mensais (VA + VT / mês)", fmt_brl(va_atual + vt_atual))

        st.markdown("#### 📄 Contracheques Importados (`dados/salario/`)")
        st.dataframe(
            df_cc[[
                "referencia", "data_pagamento", "empresa", "funcao",
                "salario_bruto", "inss_desconto", "outros_descontos",
                "total_descontos", "salario_liquido", "fgts_deposito"
            ]].rename(columns={
                "referencia": "Mês Referência",
                "data_pagamento": "Data Pagamento",
                "empresa": "Empresa",
                "funcao": "Cargo",
                "salario_bruto": "Salário Bruto",
                "inss_desconto": "INSS",
                "outros_descontos": "Gympass / Outros",
                "total_descontos": "Total Descontos",
                "salario_liquido": "Salário Líquido",
                "fgts_deposito": "Depósito FGTS"
            }).style.format({
                "Salário Bruto": "R$ {:,.2f}",
                "INSS": "R$ {:,.2f}",
                "Gympass / Outros": "R$ {:,.2f}",
                "Total Descontos": "R$ {:,.2f}",
                "Salário Líquido": "R$ {:,.2f}",
                "Depósito FGTS": "R$ {:,.2f}"
            }),
            hide_index=True,
            width="stretch"
        )
    else:
        st.info("Nenhum demonstrativo de pagamento encontrado em `dados/salario/`.")

    st.markdown("---")
    st.markdown("#### 🍱🚗 Configuração de Benefícios Fixos Mensais (Depositados todo dia 01)")
    col_b1, col_b2, col_b3 = st.columns([1, 1, 1])
    with col_b1:
        novo_va = st.number_input("Vale-Alimentação Mensal (R$ - Dia 01):", min_value=0.0, value=va_atual, step=10.0)
    with col_b2:
        novo_vt = st.number_input("Vale-Transporte Mensal (R$ - Dia 01):", min_value=0.0, value=vt_atual, step=10.0)
    with col_b3:
        novo_ativo = st.checkbox("Gerar benefícios automaticamente todo dia 01", value=benef_ativo)
        if st.button("💾 Salvar Valores de VA / VT", width="stretch"):
            database.set_config("vale_alimentacao_valor", f"{novo_va:.2f}")
            database.set_config("vale_transporte_valor", f"{novo_vt:.2f}")
            database.set_config("beneficios_ativos", "1" if novo_ativo else "0")
            database.reconcile_salaries_and_benefits()
            st.cache_data.clear()
            st.success("Benefícios mensais atualizados e recalculados!")
            st.rerun()

# ==========================================================
# ABA 6: EXTRATO CONSOLIDADO
# ==========================================================
with tab_extrato:
    st.subheader("📋 Extrato Unificado de Transações")
    
    col_search, col_cat, col_tipo = st.columns([2, 1, 1])
    with col_search:
        busca_texto = st.text_input("🔍 Pesquisar por descrição, estabelecimento ou valor...", "")
    with col_cat:
        todas_cats = ["Todas"] + sorted(df_all["categoria"].unique().tolist()) if not df_all.empty else ["Todas"]
        filtro_cat = st.selectbox("Filtrar por Categoria", todas_cats)
    with col_tipo:
        filtro_tipo = st.selectbox("Tipo de Movimentação", ["Todos", "Despesa", "Receita", "Transferência / Fatura"])

    df_view = df_filtered.copy()
    if busca_texto:
        df_view = df_view[df_view["descricao"].str.contains(busca_texto, case=False, na=False) |
                          df_view["valor"].astype(str).str.contains(busca_texto, na=False)]
    if filtro_cat != "Todas":
        df_view = df_view[df_view["categoria"] == filtro_cat]
    if filtro_tipo != "Todos":
        df_view = df_view[df_view["tipo_movimentacao"] == filtro_tipo]
        
    st.write(f"Mostrando **{len(df_view)}** transações")
    
    show_cols = ["data", "banco", "conta_tipo", "descricao", "categoria", "tipo_movimentacao", "valor", "arquivo_origem"]
    renamed = {
        "data": "Data",
        "banco": "Origem / Banco",
        "conta_tipo": "Conta",
        "descricao": "Descrição",
        "categoria": "Categoria",
        "tipo_movimentacao": "Tipo",
        "valor": "Valor (R$)",
        "arquivo_origem": "Arquivo de Origem"
    }
    
    st.dataframe(
        df_view[show_cols].rename(columns=renamed).style.format({"Valor (R$)": "R$ {:,.2f}"}),
        hide_index=True,
        width="stretch",
        height=500
    )
    
    col_exp1, col_exp2 = st.columns([1, 1])
    with col_exp1:
        csv_buffer = df_view[show_cols].rename(columns=renamed).to_csv(index=False).encode('utf-8')
        st.download_button(
            label="📥 Exportar Extrato em CSV",
            data=csv_buffer,
            file_name=f"extrato_consolidado_{datetime.now().strftime('%Y%m%d')}.csv",
            mime="text/csv",
            width="stretch"
        )
    with col_exp2:
        excel_buffer = io.BytesIO()
        with pd.ExcelWriter(excel_buffer, engine="openpyxl") as writer:
            df_view[show_cols].rename(columns=renamed).to_excel(writer, index=False, sheet_name="Extrato")
        st.download_button(
            label="📊 Exportar Extrato em Excel (.xlsx)",
            data=excel_buffer.getvalue(),
            file_name=f"extrato_consolidado_{datetime.now().strftime('%Y%m%d')}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            width="stretch"
        )

# ==========================================================
# ABA 7: CATEGORIAS & REGRAS
# ==========================================================
with tab_regras:
    st.subheader("🏷️ Gerenciador de Categorias e Aprendizado")
    st.caption("Ensine o sistema a categorizar suas transações automaticamente para todos os meses presentes e futuros.")
    
    col_rule_form, col_rule_list = st.columns([1, 1])
    
    with col_rule_form:
        st.markdown("##### ➕ Criar Nova Regra")
        with st.form("form_regra"):
            termo_chave = st.text_input("Palavra-chave ou Nome (ex: 'Mercadolivre', 'Uber', 'Compesa'):")
            categoria_escolhida = st.selectbox("Categoria:", ALL_CATEGORIES)
            tipo_escolhido = st.selectbox(
                "Tipo de Movimentação:",
                ["Despesa", "Receita", "Transferência / Fatura"]
            )
            
            btn_salvar_regra = st.form_submit_button("Salvar e Aplicar a Todas as Transações")
            if btn_salvar_regra:
                if termo_chave.strip():
                    database.save_user_rule(termo_chave.strip(), categoria_escolhida, tipo_escolhido)
                    st.cache_data.clear()
                    st.success(f"Regra salva! Transações com '{termo_chave}' foram atualizadas.")
                    st.rerun()
                else:
                    st.error("Informe a palavra-chave.")

    with col_rule_list:
        st.markdown("##### 📜 Regras Customizadas Ativas")
        regras_salvas = database.get_user_rules()
        if regras_salvas:
            regras_df = pd.DataFrame([
                {"Termo": k, "Categoria": v[0], "Tipo": v[1]}
                for k, v in regras_salvas.items()
            ])
            st.dataframe(regras_df, hide_index=True, width="stretch")
        else:
            st.info("Nenhuma regra manual cadastrada ainda. O sistema está utilizando as regras inteligentes padrão.")

    st.markdown("---")
    st.markdown("##### ✏️ Alteração Rápida de Transação Específica")
    if not df_all.empty:
        transacao_opcoes = {f"{r['data']} - {r['descricao']} (R$ {r['valor']:.2f}) [{r['categoria']}]": r["id"] for _, r in df_all.head(100).iterrows()}
        transacao_sel = st.selectbox("Selecione a transação:", list(transacao_opcoes.keys()))
        if transacao_sel:
            t_id = transacao_opcoes[transacao_sel]
            col_t1, col_t2 = st.columns([2, 1])
            with col_t1:
                nova_cat = st.selectbox("Nova Categoria:", ALL_CATEGORIES, key="select_single_cat")
            with col_t2:
                st.write("")
                st.write("")
                if st.button("Atualizar Categoria", key="btn_update_single"):
                    database.update_transaction_category(t_id, nova_cat)
                    st.cache_data.clear()
                    st.success("Categoria atualizada!")
                    st.rerun()

# ==========================================================
# ABA 8: ARQUIVOS & CONFIGURAÇÕES
# ==========================================================
with tab_arquivos:
    st.subheader("📁 Arquivos Processados & Configurações do Sistema")
    
    col_cfg1, col_cfg2 = st.columns([1, 1])
    
    with col_cfg1:
        st.markdown("#### 🔐 Senhas de PDFs Protegidos")
        st.caption("Alguns bancos (ex: Atacadão) exigem senha para abrir a fatura em PDF.")
        senhas_atuais = database.get_config("pdf_passwords", "")
        nova_senha = st.text_input("Senhas conhecidas (separadas por vírgula):", senhas_atuais)
        if st.button("Salvar Senhas"):
            database.set_config("pdf_passwords", nova_senha)
            st.success("Senhas atualizadas!")
            
    with col_cfg2:
        st.markdown("#### ⚠️ Manutenção do Banco de Dados")
        st.caption("Caso deseje limpar os dados e forçar a releitura completa de todos os extratos e contracheques.")
        if st.button("🗑️ Limpar Banco e Reprocessar Tudo", type="primary"):
            database.clear_all_data()
            with st.spinner("Reprocessando todos os arquivos da pasta dados/..."):
                scan_and_ingest_all("dados", force_reload=True)
            st.cache_data.clear()
            st.success("Banco de dados reconstruído do zero com sucesso!")
            st.rerun()

    st.markdown("---")
    st.markdown("#### 📑 Lista de Arquivos Lidos na Pasta `dados/`")
    conn = database.get_connection()
    c = conn.cursor()
    c.execute("SELECT caminho, status, total_transacoes, processado_em FROM arquivos_processados ORDER BY caminho ASC")
    files_processed = [dict(r) for r in c.fetchall()]
    conn.close()
    
    if files_processed:
        st.dataframe(
            pd.DataFrame(files_processed).rename(columns={
                "caminho": "Caminho do Arquivo",
                "status": "Status",
                "total_transacoes": "Transações Extraídas",
                "processado_em": "Data de Processamento"
            }),
            hide_index=True,
            width="stretch"
        )
    else:
        st.info("Nenhum arquivo registrado no histórico de processamento.")
