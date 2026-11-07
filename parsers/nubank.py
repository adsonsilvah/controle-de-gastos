import csv
from typing import List
from .base import Transaction
from categorizer import categorize

def clean_br_number(val: str) -> float:
    s = str(val).strip().replace("R$", "").replace(" ", "").replace(".", "")
    s = s.replace(",", ".")
    return float(s)

class NubankParser:
    @staticmethod
    def parse(file_path: str, user_rules: dict = None) -> List[Transaction]:
        transactions = []
        seen_in_file = {}
        with open(file_path, mode='r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                raw_date = row.get("date", "").strip()
                title = row.get("title", "").strip()
                raw_amount = row.get("amount", "0").strip()
                
                if not raw_date or not title:
                    continue
                
                is_negative = "-" in raw_amount
                val_clean = raw_amount.replace("-", "")
                valor = clean_br_number(val_clean)
                
                if "pagamento recebido" in title.lower():
                    cat, tipo = "Transferência / Fatura", "Transferência / Fatura"
                elif is_negative or "estorno" in title.lower():
                    cat, tipo = "Estornos & Devoluções", "Receita"
                elif "parcelamento de fatura" in title.lower():
                    cat, tipo = "Tarifas & Encargos", "Despesa"
                else:
                    cat, tipo = categorize(title, original_tipo="Saída", user_rules=user_rules)

                # Contador de ocorrência para preservar cobranças idênticas no mesmo dia dentro da mesma fatura
                sig = f"{raw_date}|{title}|{valor:.2f}"
                occ = seen_in_file.get(sig, 0) + 1
                seen_in_file[sig] = occ
                doc_id = f"occ-{occ}" if occ > 1 else ""
                
                t = Transaction(
                    data=raw_date,
                    banco="Nubank",
                    conta_tipo="Cartão de Crédito",
                    descricao=title,
                    valor=valor,
                    tipo_movimentacao=tipo,
                    categoria=cat,
                    documento=doc_id,
                    arquivo_origem=file_path
                )
                t.id = t.generate_id()
                transactions.append(t)
                
        return transactions
