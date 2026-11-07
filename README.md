# 💰 Sistema de Gestão Financeira Pessoal

Sistema local desenvolvido em **Python + Streamlit + SQLite** para consolidação, extração inteligente, previsão de gastos e planejamento financeiro pessoal a partir de extratos bancários, faturas de cartão de crédito, demonstrativos de pagamento e boletos.

---

## 🚀 Como Iniciar o Aplicativo

1. Crie o ambiente virtual e instale as dependências:
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

2. Inicie o dashboard:
```bash
./run.sh
```

O aplicativo abrirá no navegador em: **`http://localhost:8501`**

---

## 🏦 Instituições e Formatos Suportados

| Instituição / Documento | Formato | Detalhes da Extração |
| :--- | :--- | :--- |
| **Nubank** | `.csv` | Extração de faturas de cartão, parcelamentos e pagamentos de fatura. |
| **Banco do Brasil** | `.csv` | Extratos de conta corrente, transferências, pagamentos via Pix e compras no débito. |
| **Banco Inter** | `.pdf` | Faturas de cartão de crédito, compras, assinaturas recorrentes e pagamentos on-line. |
| **Cartão Atacadão** | `.pdf` | Faturas protegidas por senha com extração tabular de compras e parcelas. |
| **Caixa Econômica** | `.pdf` | Extratos gerados pelo app em formato de imagem processados via **OCR local** (`RapidOCR`). |
| **Mercado Pago** | `.pdf` | Extratos de conta com rendimentos, transferências e reservas. |
| **Demonstrativo de Pagamento (Salário)** | `.pdf` | Extração de Salário Base, Dissídio, Descontos em Folha (INSS, benefícios), Salário Líquido e FGTS. |
| **Benefícios Fixos (VA / VT)** | Automático | Lançamento mensal automático configurável para Vale-Alimentação e Vale-Transporte. |
| **Boletos Bancários** | `.pdf` | Leitura da linha digitável FEBRABAN com identificação matemática de valor e vencimento. |

---

## 🧠 Principais Funcionalidades

1. **Visão Geral & Relatórios Gráficos:**
   - Indicadores consolidados de Despesas, Receitas, Saldo Líquido e Gastos em Cartões.
   - Gráficos interativos de despesas por categoria, evolução mensal e distribuição por instituição.
2. **Previsão de Gastos & Comparativo "Previsto vs Realizado":**
   - Projeção automática para os próximos meses somando gastos fixos/assinaturas, parcelas de cartão já contratadas e média histórica variável.
   - Comparativo mensal entre o valor previsto/meta e o valor efetivamente gasto.
3. **Divisão e Organização do Salário (Planejamento Financeiro):**
   - Planejamento de alocação da renda líquida configurável em **Porcentagem (`%`)** ou **Valor Fixo (`R$`)** entre Contas Essenciais, Poupança/Reserva, Lazer e Compras.
4. **Identificação de Gastos Fixos, Assinaturas e Parcelamentos:**
   - Detecção automática de assinaturas e mensalidades recorrentes nos cartões e controle de parcelas restantes.
5. **Privacidade Total:**
   - Processamento 100% offline e local. Arquivos pessoais (`dados/`), banco de dados (`*.db`) e configurações locais (`config_local.json`) são ignorados pelo Git (`.gitignore`).
