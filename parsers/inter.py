import re
from typing import List
import pdfplumber
from .base import Transaction
from categorizer import categorize

MONTH_MAP = {
    "jan": 1, "fev": 2, "mar": 3, "abr": 4,
    "mai": 5, "jun": 6, "jul": 7, "ago": 8,
    "set": 9, "out": 10, "nov": 11, "dez": 12
}

def clean_br_number(val: str) -> float:
    s = str(val).strip().replace("R$", "").replace(" ", "").replace(".", "")
    s = s.replace(",", ".").replace("+", "").replace("-", "")
    return float(s)

class BancoInterParser:
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
            print(f"[Banco Inter] Não foi possível abrir {file_path}.")
            return []

        transactions = []
        # Ex: "16 de jul. 2026 VIVO EASY*VIVO EASY - R$ 35,00"
        # Ex: "15 de jul. 2026 PAGAMENTO ON LINE - + R$ 227,80"
        line_regex = re.compile(
            r"^(\d{2})\s+de\s+([a-zA-ZçÇ]{3})\.?\s+(\d{4})\s+(.+?)\s+-\s+(\+\s*)?R\$\s*([\d\.,]+)$",
            re.IGNORECASE
        )
        card_regex = re.compile(r"CARTÃO\s+(\d{4}\*+\d{4})", re.IGNORECASE)

        try:
            current_card = ""
            seen_in_file = {}
            for page in pdf.pages:
                text = page.extract_text() or ""
                for line in text.split("\n"):
                    line_s = line.strip()
                    if not line_s:
                        continue

                    m_card = card_regex.search(line_s)
                    if m_card:
                        current_card = m_card.group(1)
                        continue

                    m = line_regex.match(line_s)
                    if m:
                        day = int(m.group(1))
                        mon_str = m.group(2).lower()[:3]
                        year = int(m.group(3))
                        desc = m.group(4).strip()
                        is_credit_payment = bool(m.group(5)) or "pagamento on line" in desc.lower()
                        raw_val = m.group(6)

                        month = MONTH_MAP.get(mon_str, 1)
                        data_iso = f"{year:04d}-{month:02d}-{day:02d}"
                        valor = clean_br_number(raw_val)

                        if is_credit_payment:
                            cat = "Transferência / Fatura"
                            tipo = "Transferência / Fatura"
                        else:
                            cat, tipo = categorize(desc, original_tipo="Saída", user_rules=user_rules)

                        sig = f"{data_iso}|{desc}|{valor:.2f}|{current_card}"
                        occ = seen_in_file.get(sig, 0) + 1
                        seen_in_file[sig] = occ
                        doc_str = f"{current_card}" if occ == 1 else f"{current_card}-{occ}"

                        t = Transaction(
                            data=data_iso,
                            banco="Banco Inter",
                            conta_tipo="Cartão de Crédito",
                            descricao=desc,
                            valor=valor,
                            tipo_movimentacao=tipo,
                            categoria=cat,
                            documento=doc_str,
                            arquivo_origem=file_path
                        )
                        t.id = t.generate_id()
                        transactions.append(t)
        finally:
            pdf.close()

        return transactions
