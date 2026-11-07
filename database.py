import sqlite3
import os
import json
from typing import List, Dict, Optional, Tuple
from parsers.base import Transaction

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "financas.db")

def get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_connection()
    cursor = conn.cursor()
    
    # Tabela principal de transações
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS transacoes (
        id TEXT PRIMARY KEY,
        data TEXT NOT NULL,
        banco TEXT NOT NULL,
        conta_tipo TEXT NOT NULL,
        descricao TEXT NOT NULL,
        valor REAL NOT NULL,
        tipo_movimentacao TEXT NOT NULL,
        categoria TEXT NOT NULL,
        documento TEXT,
        arquivo_origem TEXT,
        criado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """)
    
    # Tabela de contracheques (Demonstrativos de Pagamento)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS contracheques (
        referencia TEXT PRIMARY KEY,
        data_pagamento TEXT NOT NULL,
        empresa TEXT,
        funcao TEXT,
        salario_bruto REAL,
        total_descontos REAL,
        salario_liquido REAL,
        fgts_deposito REAL,
        inss_desconto REAL,
        outros_descontos REAL,
        arquivo_origem TEXT,
        processado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """)
    
    # Tabela para controle de arquivos já lidos
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS arquivos_processados (
        caminho TEXT PRIMARY KEY,
        tamanho INTEGER,
        mtime REAL,
        status TEXT,
        total_transacoes INTEGER,
        processado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """)
    
    # Tabela para regras de categorização customizadas pelo usuário
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS regras_categorias (
        palavra_chave TEXT PRIMARY KEY,
        categoria TEXT NOT NULL,
        tipo_movimentacao TEXT NOT NULL
    )
    """)
    
    # Tabela para senhas e preferências
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS configuracoes (
        chave TEXT PRIMARY KEY,
        valor TEXT NOT NULL
    )
    """)

    # Tabela de previsão / meta de gastos por mês (Previsto vs Realizado)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS orcamento_mensal (
        mes_ano TEXT PRIMARY KEY,
        valor_previsto REAL NOT NULL,
        observacao TEXT
    )
    """)

    # Tabela de divisão/organização da renda (Planejamento por % ou Valor R$)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS divisao_renda (
        grupo TEXT PRIMARY KEY,
        modo TEXT NOT NULL,
        valor_config REAL NOT NULL,
        categorias_json TEXT NOT NULL,
        ordem INTEGER DEFAULT 1
    )
    """)

    # Tabela de gastos fixos / assinaturas manuais ou confirmadas
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS gastos_fixos_custom (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        nome TEXT NOT NULL UNIQUE,
        banco TEXT NOT NULL,
        valor REAL NOT NULL,
        categoria TEXT NOT NULL,
        dia_vencimento INTEGER DEFAULT 10,
        ativo INTEGER DEFAULT 1
    )
    """)
    
    # Configurações padrão (lê valores iniciais de config_local.json se existir na máquina local)
    local_cfg_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config_local.json")
    local_cfg = {}
    if os.path.exists(local_cfg_path):
        try:
            with open(local_cfg_path, "r", encoding="utf-8") as f:
                local_cfg = json.load(f)
        except Exception:
            pass

    defaults = [
        ("pdf_passwords", local_cfg.get("pdf_passwords", "")),
        ("vale_alimentacao_valor", local_cfg.get("vale_alimentacao_valor", "0.00")),
        ("vale_transporte_valor", local_cfg.get("vale_transporte_valor", "0.00")),
        ("beneficios_ativos", local_cfg.get("beneficios_ativos", "1")),
        ("salario_base_planejamento", local_cfg.get("salario_base_planejamento", "0.00"))
    ]
    for k, v in defaults:
        cursor.execute("INSERT OR IGNORE INTO configuracoes (chave, valor) VALUES (?, ?)", (k, v))

    # Divisão de renda padrão (Regra 50 / 20 / 15 / 15 personalizável em % ou R$)
    default_buckets = [
        (
            "1. Contas Essenciais, Moradia & Supermercado",
            "Percentual (%)",
            50.0,
            json.dumps(["Moradia & Contas", "Supermercado & Feira", "Saúde & Farmácia", "Educação", "Transporte & Combustível", "Casa & Construção"]),
            1
        ),
        (
            "2. Poupança, Reserva & Investimentos (Guardar)",
            "Percentual (%)",
            20.0,
            json.dumps(["POUPANCA_RESERVA"]),
            2
        ),
        (
            "3. Lazer, Restaurantes & Estilo de Vida",
            "Percentual (%)",
            15.0,
            json.dumps(["Lazer & Bem-Estar", "Alimentação & Restaurante"]),
            3
        ),
        (
            "4. Compras, Assinaturas & Outros Gastos",
            "Percentual (%)",
            15.0,
            json.dumps(["E-commerce & Compras", "Serviços & Recargas", "Tarifas & Encargos", "Outros Gastos"]),
            4
        )
    ]
    for grp, modo, val, cats, ord_idx in default_buckets:
        cursor.execute("""
        INSERT OR IGNORE INTO divisao_renda (grupo, modo, valor_config, categorias_json, ordem)
        VALUES (?, ?, ?, ?, ?)
        """, (grp, modo, val, cats, ord_idx))
    
    conn.commit()
    conn.close()

def save_transactions(transactions: List[Transaction]) -> int:
    if not transactions:
        return 0
        
    conn = get_connection()
    cursor = conn.cursor()
    
    inserted = 0
    for t in transactions:
        t_id = t.id or t.generate_id()
        try:
            cursor.execute("""
            INSERT OR IGNORE INTO transacoes 
            (id, data, banco, conta_tipo, descricao, valor, tipo_movimentacao, categoria, documento, arquivo_origem)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                t_id, t.data, t.banco, t.conta_tipo, t.descricao,
                t.valor, t.tipo_movimentacao, t.categoria, t.documento, t.arquivo_origem
            ))
            if cursor.rowcount > 0:
                inserted += 1
        except Exception as e:
            print(f"Erro ao inserir transação {t_id}: {e}")
            
    conn.commit()
    conn.close()
    return inserted

def save_contracheque(meta: Dict):
    if not meta:
        return
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
    INSERT OR REPLACE INTO contracheques
    (referencia, data_pagamento, empresa, funcao, salario_bruto, total_descontos,
     salario_liquido, fgts_deposito, inss_desconto, outros_descontos, arquivo_origem, processado_em)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
    """, (
        meta["referencia"], meta["data_pagamento"], meta["empresa"], meta["funcao"],
        meta["salario_bruto"], meta["total_descontos"], meta["salario_liquido"],
        meta["fgts_deposito"], meta["inss_desconto"], meta["outros_descontos"],
        meta["arquivo_origem"]
    ))
    conn.commit()
    conn.close()

def get_all_contracheques() -> List[Dict]:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM contracheques ORDER BY data_pagamento DESC")
    rows = [dict(r) for r in cursor.fetchall()]
    conn.close()
    return rows

def reconcile_salaries_and_benefits():
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT data_pagamento, salario_liquido, referencia FROM contracheques")
    contracheques = cursor.fetchall()
    datas_com_contracheque = {row["data_pagamento"]: row["referencia"] for row in contracheques}

    for dt_pag, ref in datas_com_contracheque.items():
        cursor.execute("""
        UPDATE transacoes
        SET descricao = ?,
            categoria = 'Transferência / Fatura',
            tipo_movimentacao = 'Transferência / Fatura'
        WHERE banco = 'Banco do Brasil'
          AND data = ?
          AND (descricao LIKE '%Salário Líquido%' OR descricao LIKE '%Transferência recebida%')
        """, (f"Repasse Salário Líquido Conta Salário BB (Já detalhado no Contracheque {ref})", dt_pag))

    conn.commit()

    beneficios_ativos = get_config("beneficios_ativos", "1") == "1"
    va_valor = float(get_config("vale_alimentacao_valor", "460.00").replace(",", "."))
    vt_valor = float(get_config("vale_transporte_valor", "250.00").replace(",", "."))

    cursor.execute("DELETE FROM transacoes WHERE arquivo_origem = 'SISTEMA_BENEFICIOS_FIXOS'")
    conn.commit()

    if beneficios_ativos:
        cursor.execute("""
        SELECT DISTINCT substr(data, 1, 7) as mes_ano
        FROM transacoes
        WHERE arquivo_origem != 'SISTEMA_BENEFICIOS_FIXOS'
          AND substr(data, 1, 7) >= '2026-08'
        ORDER BY mes_ano ASC
        """)
        meses = [r["mes_ano"] for r in cursor.fetchall() if r["mes_ano"]]
        conn.close()

        benef_txs = []
        for mes_ano in meses:
            data_dia_01 = f"{mes_ano}-01"
            if va_valor > 0:
                t_va_in = Transaction(
                    data=data_dia_01,
                    banco="Benefícios (VA / VT)",
                    conta_tipo="Vale-Alimentação",
                    descricao=f"Crédito Mensal Vale-Alimentação (Ref. {mes_ano})",
                    valor=va_valor,
                    tipo_movimentacao="Receita",
                    categoria="Benefícios (VA / VT)",
                    documento=f"VA-IN-{mes_ano}",
                    arquivo_origem="SISTEMA_BENEFICIOS_FIXOS"
                )
                t_va_in.id = t_va_in.generate_id()
                benef_txs.append(t_va_in)

                t_va_out = Transaction(
                    data=data_dia_01,
                    banco="Benefícios (VA / VT)",
                    conta_tipo="Vale-Alimentação",
                    descricao=f"Consumo Vale-Alimentação (Estabelecimentos de Comida - {mes_ano})",
                    valor=va_valor,
                    tipo_movimentacao="Despesa",
                    categoria="Alimentação & Restaurante",
                    documento=f"VA-OUT-{mes_ano}",
                    arquivo_origem="SISTEMA_BENEFICIOS_FIXOS"
                )
                t_va_out.id = t_va_out.generate_id()
                benef_txs.append(t_va_out)

            if vt_valor > 0:
                t_vt_in = Transaction(
                    data=data_dia_01,
                    banco="Benefícios (VA / VT)",
                    conta_tipo="Vale-Transporte",
                    descricao=f"Crédito Mensal Vale-Transporte (Ref. {mes_ano})",
                    valor=vt_valor,
                    tipo_movimentacao="Receita",
                    categoria="Benefícios (VA / VT)",
                    documento=f"VT-IN-{mes_ano}",
                    arquivo_origem="SISTEMA_BENEFICIOS_FIXOS"
                )
                t_vt_in.id = t_vt_in.generate_id()
                benef_txs.append(t_vt_in)

                t_vt_out = Transaction(
                    data=data_dia_01,
                    banco="Benefícios (VA / VT)",
                    conta_tipo="Vale-Transporte",
                    descricao=f"Consumo Vale-Transporte (Uber, 99 e Combustível - {mes_ano})",
                    valor=vt_valor,
                    tipo_movimentacao="Despesa",
                    categoria="Transporte & Combustível",
                    documento=f"VT-OUT-{mes_ano}",
                    arquivo_origem="SISTEMA_BENEFICIOS_FIXOS"
                )
                t_vt_out.id = t_vt_out.generate_id()
                benef_txs.append(t_vt_out)

        save_transactions(benef_txs)
    else:
        conn.close()

def get_custom_forecasts() -> Dict[str, Tuple[float, str]]:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT mes_ano, valor_previsto, observacao FROM orcamento_mensal")
    res = {r["mes_ano"]: (r["valor_previsto"], r["observacao"] or "") for r in cursor.fetchall()}
    conn.close()
    return res

def set_custom_forecast(mes_ano: str, valor_previsto: float, observacao: str = ""):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
    INSERT OR REPLACE INTO orcamento_mensal (mes_ano, valor_previsto, observacao)
    VALUES (?, ?, ?)
    """, (mes_ano, valor_previsto, observacao))
    conn.commit()
    conn.close()

def delete_custom_forecast(mes_ano: str):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM orcamento_mensal WHERE mes_ano = ?", (mes_ano,))
    conn.commit()
    conn.close()

def get_income_division() -> List[Dict]:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT grupo, modo, valor_config, categorias_json, ordem FROM divisao_renda ORDER BY ordem ASC")
    rows = []
    for r in cursor.fetchall():
        d = dict(r)
        d["categorias"] = json.loads(d["categorias_json"])
        rows.append(d)
    conn.close()
    return rows

def update_income_division(grupo: str, modo: str, valor_config: float, categorias: List[str] = None):
    conn = get_connection()
    cursor = conn.cursor()
    if categorias is not None:
        cursor.execute("""
        UPDATE divisao_renda SET modo = ?, valor_config = ?, categorias_json = ? WHERE grupo = ?
        """, (modo, valor_config, json.dumps(categorias), grupo))
    else:
        cursor.execute("""
        UPDATE divisao_renda SET modo = ?, valor_config = ? WHERE grupo = ?
        """, (modo, valor_config, grupo))
    conn.commit()
    conn.close()

def get_custom_fixed_expenses() -> List[Dict]:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM gastos_fixos_custom WHERE ativo = 1 ORDER BY valor DESC")
    rows = [dict(r) for r in cursor.fetchall()]
    conn.close()
    return rows

def add_custom_fixed_expense(nome: str, banco: str, valor: float, categoria: str, dia_vencimento: int = 10):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
    INSERT OR REPLACE INTO gastos_fixos_custom (nome, banco, valor, categoria, dia_vencimento, ativo)
    VALUES (?, ?, ?, ?, ?, 1)
    """, (nome.strip(), banco, valor, categoria, dia_vencimento))
    conn.commit()
    conn.close()

def delete_custom_fixed_expense(expense_id: int):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM gastos_fixos_custom WHERE id = ?", (expense_id,))
    conn.commit()
    conn.close()

def is_file_processed(file_path: str, mtime: float, size: int) -> bool:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
    SELECT status FROM arquivos_processados
    WHERE caminho = ? AND mtime = ? AND tamanho = ?
    """, (file_path, mtime, size))
    row = cursor.fetchone()
    conn.close()
    return row is not None and row["status"] == "OK"

def mark_file_processed(file_path: str, mtime: float, size: int, total_transacoes: int, status: str = "OK"):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
    INSERT OR REPLACE INTO arquivos_processados
    (caminho, tamanho, mtime, status, total_transacoes, processado_em)
    VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
    """, (file_path, size, mtime, status, total_transacoes))
    conn.commit()
    conn.close()

def get_all_transactions() -> List[Dict]:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
    SELECT id, data, banco, conta_tipo, descricao, valor, tipo_movimentacao, categoria, documento, arquivo_origem
    FROM transacoes
    ORDER BY data DESC
    """)
    rows = [dict(r) for r in cursor.fetchall()]
    conn.close()
    return rows

def update_transaction_category(transaction_id: str, new_category: str, new_tipo: Optional[str] = None):
    conn = get_connection()
    cursor = conn.cursor()
    if new_tipo:
        cursor.execute("UPDATE transacoes SET categoria = ?, tipo_movimentacao = ? WHERE id = ?", (new_category, new_tipo, transaction_id))
    else:
        cursor.execute("UPDATE transacoes SET categoria = ? WHERE id = ?", (new_category, transaction_id))
    conn.commit()
    conn.close()

def save_user_rule(keyword: str, category: str, tipo: str):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
    INSERT OR REPLACE INTO regras_categorias (palavra_chave, categoria, tipo_movimentacao)
    VALUES (?, ?, ?)
    """, (keyword.lower().strip(), category, tipo))
    
    cursor.execute("""
    UPDATE transacoes 
    SET categoria = ?, tipo_movimentacao = ?
    WHERE LOWER(descricao) LIKE ?
    """, (category, tipo, f"%{keyword.lower().strip()}%"))
    
    conn.commit()
    conn.close()

def get_user_rules() -> Dict[str, Tuple[str, str]]:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT palavra_chave, categoria, tipo_movimentacao FROM regras_categorias")
    rules = {row["palavra_chave"]: (row["categoria"], row["tipo_movimentacao"]) for row in cursor.fetchall()}
    conn.close()
    return rules

def get_config(key: str, default: str = "") -> str:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT valor FROM configuracoes WHERE chave = ?", (key,))
    row = cursor.fetchone()
    conn.close()
    return row["valor"] if row else default

def set_config(key: str, value: str):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("INSERT OR REPLACE INTO configuracoes (chave, valor) VALUES (?, ?)", (key, value))
    conn.commit()
    conn.close()

def clear_all_data():
    init_db()
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM transacoes")
    cursor.execute("DELETE FROM contracheques")
    cursor.execute("DELETE FROM arquivos_processados")
    conn.commit()
    conn.close()
