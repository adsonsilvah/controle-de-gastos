import re
import pandas as pd
from typing import List, Dict, Tuple

def add_months(ym: str, n: int) -> str:
    year, month = map(int, ym.split("-"))
    total = year * 12 + (month - 1) + n
    return f"{total // 12:04d}-{(total % 12) + 1:02d}"

def detect_fixed_expenses(df_all: pd.DataFrame, custom_fixed: List[Dict] = None) -> pd.DataFrame:
    """
    Identifica gastos fixos mensais (assinaturas, mensalidades, tarifas de pacote e descontos fixos)
    nos cartões de crédito, conta corrente e folha, além dos cadastrados manualmente pelo usuário.
    """
    fixed_items = []
    seen_names = set()

    # 1. Adiciona gastos fixos cadastrados manualmente pelo usuário
    if custom_fixed:
        for item in custom_fixed:
            nome_key = item["nome"].lower().strip()
            seen_names.add(nome_key)
            fixed_items.append({
                "Nome / Assinatura": item["nome"],
                "Origem / Cartão": item["banco"],
                "Categoria": item["categoria"],
                "Valor Mensal Fixo (R$)": float(item["valor"]),
                "Tipo de Recorrência": "Cadastrado pelo Usuário",
                "Frequência Detectada": "Mensal Fixo"
            })

    if df_all.empty:
        return pd.DataFrame(fixed_items)

    desp = df_all[df_all["tipo_movimentacao"] == "Despesa"].copy()

    # 2. Assinaturas / Mensalidades / Tarifas conhecidas nos dados
    known_patterns = [
        (r"vivo\s*(?:easy|lite)", "Vivo Easy (Plano Móvel)", "Assinatura Mensal no Cartão"),
        (r"tec\s*concursos", "Tec Concursos (Assinatura Estudos)", "Assinatura Mensal no Cartão"),
        (r"ifood\s*club", "iFood Club (Clube de Descontos)", "Assinatura Mensal no Cartão"),
        (r"wellhub", "Wellhub (Plano Cartão Inter)", "Assinatura Mensal no Cartão"),
        (r"spotify", "Spotify (Assinatura Música)", "Assinatura Mensal no Cartão"),
        (r"dl\*google", "Google (Assinatura no Cartão Inter)", "Assinatura Mensal no Cartão"),
        (r"google one", "Google One (Armazenamento em Nuvem)", "Assinatura Mensal no Cartão"),
        (r"anuidade diferenciada", "Anuidade Diferenciada Cartão Atacadão", "Mensalidade / Anuidade de Cartão"),
        (r"gympass", "Gympass / Wellhub (Desconto em Folha)", "Mensalidade em Folha / Benefício"),
        (r"tarifa pacote de servi", "Tarifa Pacote de Serviços BB", "Tarifa Bancária Mensal Fixa"),
        (r"netflix", "Netflix", "Assinatura Mensal no Cartão"),
        (r"amazon prime|prime video", "Amazon Prime", "Assinatura Mensal no Cartão"),
        (r"youtube", "YouTube Premium", "Assinatura Mensal no Cartão"),
    ]

    for pat, label, tipo_rec in known_patterns:
        if label.lower() in seen_names:
            continue
        matches = desp[desp["descricao"].str.contains(pat, case=False, na=False, regex=True)]
        if not matches.empty:
            latest = matches.sort_values("data", ascending=False).iloc[0]
            meses_count = matches["mes_ano"].nunique()
            seen_names.add(label.lower())
            fixed_items.append({
                "Nome / Assinatura": label,
                "Origem / Cartão": latest["banco"],
                "Categoria": latest["categoria"],
                "Valor Mensal Fixo (R$)": float(latest["valor"]),
                "Tipo de Recorrência": tipo_rec,
                "Frequência Detectada": f"{meses_count} mês(es) registrado(s)"
            })

    # 3. Detecção automática de valores idênticos em múltiplos meses no Cartão de Crédito (sem ser parcelamento)
    cards_no_parc = desp[
        (desp["conta_tipo"] == "Cartão de Crédito") &
        (~desp["descricao"].str.contains(r"\d+/\d+", regex=True))
    ]
    if not cards_no_parc.empty:
        grouped = cards_no_parc.groupby(["descricao", "banco", "categoria", "valor"])["mes_ano"].nunique().reset_index()
        recurring = grouped[grouped["mes_ano"] >= 2]
        for _, r in recurring.iterrows():
            desc_lower = r["descricao"].lower()
            if any(k in desc_lower for k in seen_names) or any(re.search(p[0], desc_lower) for p in known_patterns):
                continue
            seen_names.add(desc_lower)
            fixed_items.append({
                "Nome / Assinatura": r["descricao"],
                "Origem / Cartão": r["banco"],
                "Categoria": r["categoria"],
                "Valor Mensal Fixo (R$)": float(r["valor"]),
                "Tipo de Recorrência": "Valor Idêntico Recorrente no Cartão",
                "Frequência Detectada": f"{r['mes_ano']} meses seguidos"
            })

    return pd.DataFrame(fixed_items)


def extract_installment_plans(df_all: pd.DataFrame) -> Tuple[pd.DataFrame, Dict[str, float]]:
    """
    Identifica todas as compras parceladas nos cartões de crédito (ex: 'Parcela 1/4', '- 2/3', '- 6/12'),
    calcula quantas parcelas faltam e projeta o impacto exato nos meses futuros.
    Retorna:
      - DataFrame com o resumo de cada parcelamento
      - Dicionário { 'YYYY-MM': soma_das_parcelas_naquele_mes }
    """
    if df_all.empty:
        return pd.DataFrame(), {}

    desp = df_all[
        (df_all["tipo_movimentacao"] == "Despesa") &
        (df_all["conta_tipo"] == "Cartão de Crédito")
    ].copy()

    if desp.empty:
        return pd.DataFrame(), {}

    # Captura padrões "Parcela X/Y" ou "- X/Y"
    parc_regex = re.compile(r"(?:-?\s*Parcela\s+|-+\s*)(\d+)/(\d+)\s*$", re.IGNORECASE)

    plans = {}
    monthly_committed = {}

    for _, row in desp.sort_values("data").iterrows():
        desc = row["descricao"].strip()
        m = parc_regex.search(desc)
        if not m:
            continue

        p_atual = int(m.group(1))
        p_total = int(m.group(2))
        base_name = parc_regex.sub("", desc).strip(" -")
        banco = row["banco"]
        valor = float(row["valor"])
        mes_ano = row["mes_ano"]

        # Registra a parcela já existente no próprio mês em que ocorreu
        monthly_committed[mes_ano] = monthly_committed.get(mes_ano, 0.0) + valor

        plan_key = f"{banco}|{base_name.lower()}|{p_total}"
        if plan_key not in plans or p_atual >= plans[plan_key]["p_atual"]:
            plans[plan_key] = {
                "Compra / Descrição": base_name,
                "Cartão": banco,
                "Categoria": row["categoria"],
                "Valor da Parcela (R$)": valor,
                "p_atual": p_atual,
                "p_total": p_total,
                "Última Parcela Lida": f"{p_atual}/{p_total}",
                "Mês da Última Leitura": mes_ano,
                "Parcelas Restantes": max(0, p_total - p_atual),
                "Saldo Restante a Pagar (R$)": round(max(0, p_total - p_atual) * valor, 2),
                "Status": "Ativo (Em Andamento)" if p_atual < p_total else "Quitado / Finalizado"
            }

    # Projeta as parcelas restantes nos meses seguintes ao último mês lido
    for plan in plans.values():
        restantes = plan["Parcelas Restantes"]
        ultimo_mes = plan["Mês da Última Leitura"]
        valor = plan["Valor da Parcela (R$)"]
        if restantes > 0:
            mes_fim = add_months(ultimo_mes, restantes)
            plan["Término Previsto"] = mes_fim
            for step in range(1, restantes + 1):
                m_fut = add_months(ultimo_mes, step)
                monthly_committed[m_fut] = monthly_committed.get(m_fut, 0.0) + valor
        else:
            plan["Término Previsto"] = f"{ultimo_mes} (Concluído)"

    df_plans = pd.DataFrame(list(plans.values()))
    if not df_plans.empty:
        df_plans = df_plans.drop(columns=["p_atual", "p_total"]).sort_values(
            by=["Status", "Valor da Parcela (R$)"], ascending=[True, False]
        )

    return df_plans, monthly_committed


def build_forecast_and_comparison(
    df_all: pd.DataFrame,
    custom_forecasts: Dict[str, Tuple[float, str]] = None,
    custom_fixed: List[Dict] = None,
    include_inss: bool = True
) -> Tuple[pd.DataFrame, Dict]:
    """
    Constrói a tabela completa de Previsão de Gastos e o comparativo 'Previsto vs Realizado'
    para os meses históricos/atuais e para os próximos 6 meses futuros.
    """
    custom_forecasts = custom_forecasts or {}
    df_fixed = detect_fixed_expenses(df_all, custom_fixed)
    df_plans, monthly_installments = extract_installment_plans(df_all)

    # Soma dos gastos fixos mensais contínuos (excluindo Anuidade Atacadão que já está nas parcelas 6/12)
    soma_assinaturas_fixas = 0.0
    if not df_fixed.empty:
        for _, r in df_fixed.iterrows():
            if "anuidade diferenciada" not in r["Nome / Assinatura"].lower():
                soma_assinaturas_fixas += float(r["Valor Mensal Fixo (R$)"])

    if df_all.empty:
        return pd.DataFrame(), {}

    desp = df_all[df_all["tipo_movimentacao"] == "Despesa"].copy()
    if not include_inss:
        desp = desp[desp["categoria"] != "Impostos & INSS (Folha)"]

    # Calcula média mensal histórica dos meses fechados (2026-08, 2026-09, 2026-10)
    meses_fechados = ["2026-08", "2026-09", "2026-10"]
    desp_fechados = desp[desp["mes_ano"].isin(meses_fechados)]

    # Despesas variáveis = Total dos meses fechados menos parcelas de cartão, benefícios fixos e INSS
    if not desp_fechados.empty:
        var_mask = (
            (desp_fechados["arquivo_origem"] != "SISTEMA_BENEFICIOS_FIXOS") &
            (desp_fechados["categoria"] != "Impostos & INSS (Folha)") &
            (~desp_fechados["descricao"].str.contains(r"\d+/\d+", regex=True))
        )
        media_variavel = desp_fechados[var_mask].groupby("mes_ano")["valor"].sum().mean()
        if pd.isna(media_variavel):
            media_variavel = 1500.0
    else:
        media_variavel = 1500.0

    # Benefícios mensais fixos (VA + VT)
    benef_mensal = desp[desp["arquivo_origem"] == "SISTEMA_BENEFICIOS_FIXOS"].groupby("mes_ano")["valor"].sum().median()
    if pd.isna(benef_mensal):
        benef_mensal = 710.0

    # INSS médio em folha
    inss_mensal = 285.47 if include_inss else 0.0

    # Lista de meses: de 2026-08 até 6 meses à frente do último mês com lançamento
    meses_existentes = sorted([m for m in desp["mes_ano"].unique() if m >= "2026-08"])
    ultimo_mes_dados = meses_existentes[-1] if meses_existentes else "2026-11"
    meses_futuros = [add_months(ultimo_mes_dados, i) for i in range(1, 7)]
    todos_meses = sorted(list(set(meses_existentes + meses_futuros)))

    realizado_por_mes = desp.groupby("mes_ano")["valor"].sum().to_dict()

    rows = []
    for m in todos_meses:
        parcelas_mes = round(monthly_installments.get(m, 0.0), 2)
        fixos_base = round(soma_assinaturas_fixas + benef_mensal + inss_mensal, 2)
        estimativa_var = round(media_variavel, 2)
        previsto_auto = round(fixos_base + parcelas_mes + estimativa_var, 2)

        if m in custom_forecasts:
            previsto_final = round(float(custom_forecasts[m][0]), 2)
            origem_prev = f"Meta Manual ({custom_forecasts[m][1]})" if custom_forecasts[m][1] else "Meta Manual Definida"
        else:
            previsto_final = previsto_auto
            origem_prev = "Projeção Automática"

        realizado = round(realizado_por_mes.get(m, 0.0), 2)
        diferenca = round(previsto_final - realizado, 2)

        if m > ultimo_mes_dados and realizado == 0:
            status = "⏳ Mês Futuro (Apenas Previsão)"
        elif m == ultimo_mes_dados:
            if diferenca >= 0:
                status = f"🟢 Em Andamento (Restam R$ {diferenca:,.2f} da previsão)"
            else:
                status = f"🔴 Acima do Previsto em R$ {abs(diferenca):,.2f}"
        else:
            if diferenca >= 0:
                status = f"✅ Economizou R$ {diferenca:,.2f} vs Previsto"
            else:
                status = f"⚠️ Gastou R$ {abs(diferenca):,.2f} acima do Previsto"

        rows.append({
            "Mês/Ano": m,
            "Fixos + VA/VT + Folha (R$)": fixos_base,
            "Parcelas de Cartão no Mês (R$)": parcelas_mes,
            "Estimativa Variável (R$)": estimativa_var,
            "Previsto / Meta Total (R$)": previsto_final,
            "Gasto Realizado (R$)": realizado,
            "Diferença (Previsto - Realizado)": diferenca,
            "Origem da Previsão": origem_prev,
            "Status do Mês": status
        })

    summary_info = {
        "soma_assinaturas_fixas": round(soma_assinaturas_fixas, 2),
        "benef_mensal": round(benef_mensal, 2),
        "inss_mensal": round(inss_mensal, 2),
        "media_variavel": round(media_variavel, 2),
        "ultimo_mes_dados": ultimo_mes_dados
    }

    return pd.DataFrame(rows), summary_info


def calculate_income_division(
    df_month: pd.DataFrame,
    renda_base: float,
    division_rules: List[Dict],
    ignore_benefits_in_salary_split: bool = True
) -> pd.DataFrame:
    """
    Calcula a divisão planejada da renda (Salário Líquido ou Renda do Mês) vs o que foi
    efetivamente gasto em cada grupo no mês selecionado, aceitando regras em % ou Valor Fixo (R$).
    """
    if not df_month.empty:
        desp_mes = df_month[df_month["tipo_movimentacao"] == "Despesa"].copy()
        if ignore_benefits_in_salary_split:
            desp_mes = desp_mes[
                (desp_mes["arquivo_origem"] != "SISTEMA_BENEFICIOS_FIXOS") &
                (desp_mes["categoria"] != "Impostos & INSS (Folha)")
            ]
    else:
        desp_mes = pd.DataFrame()

    total_despesas_mes = float(desp_mes["valor"].sum()) if not desp_mes.empty else 0.0
    saldo_guardado_real = max(0.0, renda_base - total_despesas_mes)

    result_rows = []
    for rule in division_rules:
        grupo = rule["grupo"]
        modo = rule["modo"]
        val_cfg = float(rule["valor_config"])
        cats = rule["categorias"]

        if "Percentual" in modo:
            valor_planejado = round(renda_base * (val_cfg / 100.0), 2)
            pct_planejado = val_cfg
            regra_str = f"{val_cfg:.1f}% da Renda"
        else:
            valor_planejado = round(val_cfg, 2)
            pct_planejado = round((val_cfg / renda_base * 100.0), 1) if renda_base > 0 else 0.0
            regra_str = f"Fixo R$ {val_cfg:,.2f}"

        if "POUPANCA_RESERVA" in cats:
            gasto_real = round(saldo_guardado_real, 2)
            diferenca = round(gasto_real - valor_planejado, 2)
            if gasto_real >= valor_planejado:
                status = f"🟢 Meta Atingida (+R$ {diferenca:,.2f} guardado)"
            else:
                status = f"🟡 Faltam R$ {abs(diferenca):,.2f} para a meta de poupança"
        else:
            if not desp_mes.empty:
                gasto_real = round(float(desp_mes[desp_mes["categoria"].isin(cats)]["valor"].sum()), 2)
            else:
                gasto_real = 0.0
            diferenca = round(valor_planejado - gasto_real, 2)
            if gasto_real <= valor_planejado * 0.85:
                status = f"🟢 Dentro do Limite (Restam R$ {diferenca:,.2f})"
            elif gasto_real <= valor_planejado:
                status = f"🟡 No Limite (Restam R$ {diferenca:,.2f})"
            else:
                status = f"🔴 Ultrapassou R$ {abs(diferenca):,.2f}"

        pct_real = round((gasto_real / renda_base * 100.0), 1) if renda_base > 0 else 0.0

        result_rows.append({
            "Grupo de Destino": grupo,
            "Regra Definida": regra_str,
            "Ideal / Planejado (R$)": valor_planejado,
            "% Planejado": f"{pct_planejado:.1f}%",
            "Realizado no Mês (R$)": gasto_real,
            "% Real da Renda": f"{pct_real:.1f}%",
            "Saldo / Diferença (R$)": diferenca,
            "Status": status,
            "Categorias Incluídas": ", ".join(cats) if "POUPANCA_RESERVA" not in cats else "Saldo Positivo Não Gasto / Reserva"
        })

    return pd.DataFrame(result_rows)
