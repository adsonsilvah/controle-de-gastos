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

class AtacadaoParser:
    @staticmethod
    def parse(file_path: str, passwords: List[str] = None, user_rules: dict = None) -> List[Transaction]:
        passwords = passwords or [""]
        pdf = None
        for pw in passwords:
            try:
                pdf = pdfplumber.open(file_path, password=pw if pw else None)
                _ = len(pdf.pages)
                break
            except Exception:
                pdf = None
                continue
                
        if not pdf:
            print(f"[Atacadão] Não foi possível abrir {file_path} com as senhas fornecidas.")
            return []
            
        transactions = []
        try:
            full_text = "\n".join([page.extract_text() or "" for page in pdf.pages])
            
            year_match = re.search(r"VENCIMENTO[\s\S]*?(\d{2})/(\d{2})/(\d{4})", full_text)
            if year_match:
                invoice_year = int(year_match.group(3))
                invoice_month = int(year_match.group(2))
            else:
                invoice_year = datetime.now().year
                invoice_month = 1
                
            line_pattern = re.compile(r"^(\d{2}/\d{2})\s+(.+?)\s+([\d\.,]+-?)$")
            
            capturing = False
            for line in full_text.split("\n"):
                line_str = line.strip()
                if "LANÇAMENTOS NO BRASIL" in line_str or "LANÇAMENTOS" in line_str:
                    capturing = True
                    continue
                if capturing and "TOTAL DA FATURA" in line_str:
                    capturing = False
                    continue
                    
                if capturing:
                    match = line_pattern.match(line_str)
                    if match:
                        data_dm = match.group(1)
                        desc = match.group(2).strip()
                        raw_val = match.group(3).strip()
                        
                        if "saldo fatura anterior" in desc.lower():
                            continue
                            
                        day, month = map(int, data_dm.split("/"))
                        if month > invoice_month and (month - invoice_month) > 6:
                            trans_year = invoice_year - 1
                        else:
                            trans_year = invoice_year

                        # Se for parcela 2/N, 3/N etc. com data antiga da compra original, alinha ao mês de competência da fatura
                        parc_match = re.search(r"-\s*(\d+)/(\d+)$", desc)
                        if parc_match and int(parc_match.group(1)) > 1 and month != invoice_month:
                            p_atual = int(parc_match.group(1))
                            total_months = (trans_year * 12 + (month - 1)) + (p_atual - 1)
                            eff_year = total_months // 12
                            eff_month = (total_months % 12) + 1
                            day_clamped = min(day, 28)
                            data_iso = f"{eff_year:04d}-{eff_month:02d}-{day_clamped:02d}"
                        else:
                            data_iso = f"{trans_year:04d}-{month:02d}-{day:02d}"
                        
                        valor = clean_br_number(raw_val)
                        is_credit = raw_val.endswith("-") or "pagamento de fatura" in desc.lower()
                        
                        if is_credit:
                            cat = "Transferência / Fatura"
                            tipo = "Transferência / Fatura"
                        else:
                            cat, tipo = categorize(desc, original_tipo="Saída", user_rules=user_rules)
                            
                        t = Transaction(
                            data=data_iso,
                            banco="Cartão Atacadão",
                            conta_tipo="Cartão de Crédito",
                            descricao=desc,
                            valor=valor,
                            tipo_movimentacao=tipo,
                            categoria=cat,
                            documento="",
                            arquivo_origem=file_path
                        )
                        t.id = t.generate_id()
                        transactions.append(t)
        finally:
            pdf.close()
            
        return transactions
