import os
import json
import re
from typing import Tuple

LOCAL_CONFIG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config_local.json")

def _load_local_rules() -> dict:
    if os.path.exists(LOCAL_CONFIG_PATH):
        try:
            with open(LOCAL_CONFIG_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
                return {k: tuple(v) for k, v in data.get("regras_locais", {}).items()}
        except Exception:
            pass
    return {}

DEFAULT_RULES = [
    # 1. E-commerce & Compras Online
    (
        "E-commerce & Compras",
        "Despesa",
        [
            r"mercadolivre", r"mercado livre", r"mercado\*", r"mp\*",
            r"americanas", r"amazon", r"shopee", r"magalu", r"magazine luiza",
            r"aliexpress", r"shein", r"riachuelo", r"renner", r"c&a", r"zara",
            r"\blasa\b", r"marketplace"
        ]
    ),
    # 2. Rendimentos & Investimentos
    (
        "Rendimentos & Investimentos",
        "Receita",
        [
            r"rendimentos", r"correcao\s*monetaria", r"correcaomonetaria",
            r"credito\s*juros", r"dividendos", r"jcp", r"cdi", r"tesouro direto"
        ]
    ),
    # 3. Transferências / Fatura
    (
        "Transferência / Fatura",
        "Transferência / Fatura",
        [
            r"pagamento recebido", r"pagamento de fatura", r"banco csf",
            r"nu pagamentos", r"dinheiro reservado emerg",
            r"parcelamento de fatura", r"repasse sal[aá]rio"
        ]
    ),
    # 4. Supermercado & Feira
    (
        "Supermercado & Feira",
        "Despesa",
        [
            r"atacadao", r"atacarejo", r"mercadinho",
            r"supermercado", r"hipermercado", r"atc \d+",
            r"assa[ií]", r"hortifruti",
            r"padaria", r"panificadora", r"acougue", r"frigorifico"
        ]
    ),
    # 5. Alimentação & Restaurante
    (
        "Alimentação & Restaurante",
        "Despesa",
        [
            r"ifood", r"ifd\*", r"restaurante", r"espetaria", r"pizzaria", r"lanches",
            r"hamburguer", r"burguer", r"burger",
            r"churrascaria", r"99 food", r"bar e petiscaria", r"acai",
            r"sorveteria", r"pastelaria",
            r"cafeteria", r"salgados", r"vale-alimenta[cç][aã]o"
        ]
    ),
    # 6. Transporte & Combustível
    (
        "Transporte & Combustível",
        "Despesa",
        [
            r"\buber\b", r"99app", r"99 app", r"99 pop", r"posto",
            r"combustivel", r"gasolina", r"ipiranga", r"shell",
            r"br distribuidora", r"estacionamento", r"pedagio",
            r"vale-transporte"
        ]
    ),
    # 7. Moradia & Contas
    (
        "Moradia & Contas",
        "Despesa",
        [
            r"compesa", r"celpe", r"neoenergia", r"enel", r"coelba", r"sabesp",
            r"pgto conta .gua", r"agua mineral", r"hidra", r"condominio",
            r"aluguel", r"internet", r"claro", r"vivo", r"\btim\b",
            r"energia", r"iptu"
        ]
    ),
    # 8. Educação
    (
        "Educação",
        "Despesa",
        [
            r"universidade", r"faculdade", r"ufpe", r"ufrpe",
            r"colegio", r"escola", r"curso", r"udemy", r"alura", r"livraria",
            r"tec concursos", r"concursos"
        ]
    ),
    # 9. Lazer & Bem-Estar
    (
        "Lazer & Bem-Estar",
        "Despesa",
        [
            r"sesc", r"gympass", r"wellhub", r"totalpass", r"cinema",
            r"ingresso", r"academia", r"smart fit", r"parque",
            r"teatro", r"clube", r"viagem", r"hotel"
        ]
    ),
    # 10. Saúde & Farmácia
    (
        "Saúde & Farmácia",
        "Despesa",
        [
            r"farmacia", r"drogaria", r"pague menos", r"drogasil",
            r"centro diagnostico", r"diagnostico", r"laboratorio",
            r"hospital", r"clinica", r"consulta",
            r"dentista", r"otica", r"unimed"
        ]
    ),
    # 11. Casa & Construção
    (
        "Casa & Construção",
        "Despesa",
        [
            r"cimento", r"material de construcao",
            r"tintas", r"ferragens", r"leroy merlin"
        ]
    ),
    # 12. Serviços & Assinaturas
    (
        "Serviços & Recargas",
        "Despesa",
        [
            r"recargapay", r"google", r"apple", r"netflix", r"spotify", r"youtube"
        ]
    ),
    # 13. Impostos & Descontos em Folha
    (
        "Impostos & INSS (Folha)",
        "Despesa",
        [
            r"\binss\b", r"diferen[cç]a de inss", r"\birrf\b", r"imposto de renda"
        ]
    ),
    # 14. Tarifas & Encargos Bancários
    (
        "Tarifas & Encargos",
        "Despesa",
        [
            r"tarifa pacote", r"tarifa de servico", r"anuidade diferenciada",
            r"anuidade", r"\biof\b", r"juros rotativo", r"multa", r"taxa de manutencao"
        ]
    ),
    # 15. Salário & Benefícios
    (
        "Salário & Proventos",
        "Receita",
        [
            r"sal[aá]rio base", r"sal[aá]rio l[ií]quido", r"diss[ií]dio",
            r"provento", r"remuneracao", r"folha de pag"
        ]
    ),
    (
        "Benefícios (VA / VT)",
        "Receita",
        [
            r"cr[eé]dito vale-alimenta[cç][aã]o", r"cr[eé]dito vale-transporte"
        ]
    )
]

def categorize(description: str, original_tipo: str = "", user_rules: dict = None) -> Tuple[str, str]:
    """
    Retorna (categoria, tipo_movimentacao) com base na descrição e regras.
    Prioriza regras manuais salvas pelo usuário e configurações locais (não versionadas).
    """
    desc_clean = description.lower()
    
    # 1. Checa regras customizadas do banco SQLite
    if user_rules:
        for keyword, (cat, tipo) in user_rules.items():
            if keyword.lower() in desc_clean:
                return cat, tipo

    # 2. Checa regras locais privadas (config_local.json)
    local_rules = _load_local_rules()
    for keyword, (cat, tipo) in local_rules.items():
        if keyword.lower() in desc_clean:
            return cat, tipo

    # 3. Checa regras padrão genéricas
    for cat, default_tipo, patterns in DEFAULT_RULES:
        for pat in patterns:
            if re.search(pat, desc_clean):
                tipo = default_tipo
                return cat, tipo

    # 4. Fallback inteligente baseado no tipo original do banco
    if original_tipo == "Entrada" or "cred" in desc_clean or "recebido" in desc_clean:
        return "Outras Receitas", "Receita"
    elif original_tipo == "Transferência / Fatura":
        return "Transferências", "Transferência / Fatura"
    else:
        return "Outros Gastos", "Despesa"
