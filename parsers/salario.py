import re
from datetime import datetime
from typing import List, Tuple, Optional, Dict
import pdfplumber
from .base import Transaction
from categorizer import categorize

def clean_br_number(val: str) -> float:
    s = str(val).strip().replace("R$", "").replace(" ", "").replace(".", "")
    s = s.replace(",", ".").replace("-", "")
    return float(s)

class SalarioParser:
    @staticmethod
    def parse_full(file_path: str, user_rules: dict = None) -> Tuple[List[Transaction], Optional[Dict]]:
        """
        Extrai as transações do Demonstrativo de Pagamento (proventos e descontos em folha)
        e também um resumo estruturado do contracheque (incluindo FGTS e salário líquido).
        """
        transactions = []
        metadata = None

        try:
            with pdfplumber.open(file_path) as pdf:
                full_text_layout = "\n".join([p.extract_text(layout=True) or "" for p in pdf.pages])
                if "Demonstrativo de Pagamento" not in full_text_layout:
                    return [], None

                lines = full_text_layout.split("\n")

                empresa = "Empresa Empregadora"
                funcao = ""
                referencia = ""
                data_pagamento_iso = datetime.now().strftime("%Y-%m-%d")

                # Extrai cabeçalhos
                for i, l in enumerate(lines):
                    if "EMPRESA" in l and "CNPJ" in l:
                        for j in range(i + 1, min(i + 4, len(lines))):
                            if lines[j].strip():
                                m_emp = re.match(r"^\s*(.+?)\s+\d{2}\.\d{3}\.\d{3}", lines[j])
                                if m_emp:
                                    empresa = m_emp.group(1).strip()
                                break
                    if "FUNÇÃO" in l:
                        for j in range(i + 1, min(i + 4, len(lines))):
                            if lines[j].strip():
                                parts = re.split(r"\s{2,}", lines[j].strip())
                                if len(parts) >= 3:
                                    funcao = parts[2].strip()
                                break
                    if "REFERÊNCIA" in l:
                        for j in range(i + 1, min(i + 4, len(lines))):
                            if lines[j].strip():
                                m_ref = re.search(r"(\d{2}/[a-zA-ZçÇ]+/\d{4})", lines[j])
                                if m_ref:
                                    referencia = m_ref.group(1)
                                break
                    if "DATA DE PAGAMENTO" in l:
                        for j in range(i + 1, min(i + 4, len(lines))):
                            if lines[j].strip():
                                m_dt = re.search(r"(\d{2}/\d{2}/\d{4})", lines[j])
                                if m_dt:
                                    dt = datetime.strptime(m_dt.group(1), "%d/%m/%Y")
                                    data_pagamento_iso = dt.strftime("%Y-%m-%d")
                                break

                # Determina a posição da coluna DESCONTOS no cabeçalho da tabela
                desconto_col_idx = 58
                for l in lines:
                    if "VENCIMENTOS" in l and "DESCONTOS" in l and "CONTA" in l:
                        desconto_col_idx = l.find("DESCONTOS") - 3
                        break

                in_items = False
                in_base = False
                fgts_total = 0.0
                inss_total = 0.0
                outros_desc_total = 0.0
                tot_venc = 0.0
                tot_desc = 0.0
                tot_liq = 0.0

                item_regex = re.compile(r"^\s*(\d{4})\s+(.+?)\s+([\d\.,]+)\s*$")

                for l in lines:
                    l_strip = l.strip()
                    if not l_strip:
                        continue

                    if "CONTA" in l_strip and "VENCIMENTOS" in l_strip and "DESCONTOS" in l_strip:
                        in_items = True
                        in_base = False
                        continue

                    if "BASE / OUTROS" in l_strip:
                        in_items = False
                        in_base = True
                        continue

                    if l_strip.startswith("VENCIMENTOS") and "LÍQUIDO" in l_strip:
                        in_items = False
                        in_base = False
                        continue

                    if l_strip.startswith("TOTAIS"):
                        nums = re.findall(r"[\d\.,]+", l_strip)
                        if len(nums) >= 3:
                            tot_venc = clean_br_number(nums[0])
                            tot_desc = clean_br_number(nums[1])
                            tot_liq = clean_br_number(nums[2])
                        continue

                    if in_items:
                        m_item = item_regex.match(l)
                        if m_item:
                            cod = m_item.group(1)
                            raw_desc = m_item.group(2).strip()
                            # Remove quantidade numérica no final da descrição se houver (ex: "Salário Base   220")
                            desc_clean = re.sub(r"\s+\d+$", "", raw_desc).strip()
                            val_str = m_item.group(3)
                            valor = clean_br_number(val_str)

                            # Posição onde o valor aparece na linha
                            val_pos = l.rfind(val_str)
                            is_desconto = val_pos >= desconto_col_idx

                            ref_label = f" (Ref. {referencia})" if referencia else ""

                            if is_desconto:
                                full_desc = f"{desc_clean} - Desconto em Folha{ref_label}"
                                cat, _ = categorize(desc_clean, original_tipo="Saída", user_rules=user_rules)
                                if "inss" in desc_clean.lower():
                                    cat = "Impostos & INSS (Folha)"
                                    inss_total += valor
                                else:
                                    outros_desc_total += valor
                                t = Transaction(
                                    data=data_pagamento_iso,
                                    banco="Contracheque / Salário",
                                    conta_tipo="Folha de Pagamento",
                                    descricao=full_desc,
                                    valor=valor,
                                    tipo_movimentacao="Despesa",
                                    categoria=cat,
                                    documento=f"{cod}-{referencia}",
                                    arquivo_origem=file_path
                                )
                                t.id = t.generate_id()
                                transactions.append(t)
                            else:
                                full_desc = f"{desc_clean} - {empresa}{ref_label}"
                                t = Transaction(
                                    data=data_pagamento_iso,
                                    banco="Contracheque / Salário",
                                    conta_tipo="Folha de Pagamento",
                                    descricao=full_desc,
                                    valor=valor,
                                    tipo_movimentacao="Receita",
                                    categoria="Salário & Proventos",
                                    documento=f"{cod}-{referencia}",
                                    arquivo_origem=file_path
                                )
                                t.id = t.generate_id()
                                transactions.append(t)

                    elif in_base:
                        # Captura depósito de FGTS do mês (códigos 1330 e 1350)
                        m_base = item_regex.match(l)
                        if m_base:
                            cod = m_base.group(1)
                            val_str = m_base.group(3)
                            if cod in ("1330", "1350"):
                                fgts_total += clean_br_number(val_str)

                metadata = {
                    "referencia": referencia or data_pagamento_iso[:7],
                    "data_pagamento": data_pagamento_iso,
                    "empresa": empresa,
                    "funcao": funcao,
                    "salario_bruto": tot_venc,
                    "total_descontos": tot_desc,
                    "salario_liquido": tot_liq,
                    "fgts_deposito": round(fgts_total, 2),
                    "inss_desconto": round(inss_total, 2),
                    "outros_descontos": round(outros_desc_total, 2),
                    "arquivo_origem": file_path
                }

        except Exception as e:
            print(f"[Salário] Erro ao ler {file_path}: {e}")

        return transactions, metadata

    @classmethod
    def parse(cls, file_path: str, user_rules: dict = None) -> List[Transaction]:
        txs, _ = cls.parse_full(file_path, user_rules=user_rules)
        return txs
