import re
from datetime import datetime
from typing import List
import pdfplumber
from .base import Transaction
from categorizer import categorize

def clean_br_number(val: str) -> float:
    s = str(val).strip().replace("R$", "").replace(" ", "").replace(".", "")
    s = s.replace(",", ".").replace("-", "")
    return float(s)

class MercadoPagoParser:
    @staticmethod
    def parse(file_path: str, user_rules: dict = None) -> List[Transaction]:
        transactions = []
        try:
            with pdfplumber.open(file_path) as pdf:
                for page in pdf.pages:
                    lines = page.extract_text(layout=True).split("\n")
                    consumed = set()
                    
                    for i, line in enumerate(lines):
                        date_match = re.search(r"(\d{2}-\d{2}-\d{4})", line)
                        if date_match and "Data de geração" not in line and "Periodo:" not in line:
                            raw_date = date_match.group(1)
                            try:
                                dt = datetime.strptime(raw_date, "%d-%m-%Y")
                                data_iso = dt.strftime("%Y-%m-%d")
                            except Exception:
                                data_iso = raw_date
                                
                            amounts = re.findall(r"R\$\s*(-?[\d\.,]+)", line)
                            raw_val = amounts[0] if amounts else "0"
                            is_negative = "-" in raw_val
                            valor = clean_br_number(raw_val)
                            
                            op_match = re.search(r"\b(\d{11,15})\b", line)
                            op_id = op_match.group(1) if op_match else ""
                            
                            desc_parts = []
                            # Linha anterior (se não consumida e não for cabeçalho)
                            if i > 0 and (i - 1) not in consumed:
                                prev = lines[i-1].strip()
                                if prev and "DETALHE" not in prev and "Data  Descrição" not in prev:
                                    desc_parts.append(prev)
                                    consumed.add(i-1)
                                    
                            # Parte do meio da linha atual
                            mid = line
                            mid = re.sub(r"^\s*\d{2}-\d{2}-\d{4}", "", mid)
                            if op_id:
                                mid = mid.split(op_id)[0]
                            else:
                                mid = mid.split("R$")[0]
                            mid = mid.strip()
                            if mid:
                                desc_parts.append(mid)
                            consumed.add(i)
                            
                            # Linha seguinte
                            if i + 1 < len(lines):
                                nxt = lines[i+1].strip()
                                if nxt and not re.search(r"\d{2}-\d{2}-\d{4}", nxt) and "Data de" not in nxt:
                                    desc_parts.append(nxt)
                                    consumed.add(i+1)
                                    
                            full_desc = " ".join(desc_parts).strip()
                            full_desc = re.sub(r"\s+", " ", full_desc)
                            
                            if is_negative:
                                tipo_banco = "Saída"
                            else:
                                tipo_banco = "Entrada"
                                
                            cat, tipo = categorize(full_desc, original_tipo=tipo_banco, user_rules=user_rules)
                            
                            t = Transaction(
                                data=data_iso,
                                banco="Mercado Pago",
                                conta_tipo="Conta Corrente",
                                descricao=full_desc,
                                valor=valor,
                                tipo_movimentacao=tipo,
                                categoria=cat,
                                documento=op_id,
                                arquivo_origem=file_path
                            )
                            t.id = t.generate_id()
                            transactions.append(t)
        except Exception as e:
            print(f"[Mercado Pago] Erro ao ler {file_path}: {e}")
            
        return transactions
