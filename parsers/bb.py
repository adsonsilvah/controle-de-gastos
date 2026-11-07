import csv
import re
from datetime import datetime
from typing import List
from .base import Transaction
from categorizer import categorize

def clean_br_number(val: str) -> float:
    s = str(val).strip().replace("R$", "").replace(" ", "").replace(".", "")
    s = s.replace(",", ".")
    return float(s)

class BancoDoBrasilParser:
    @staticmethod
    def parse(file_path: str, user_rules: dict = None) -> List[Transaction]:
        transactions = []
        
        encodings = ["latin1", "cp1252", "utf-8"]
        content = None
        for enc in encodings:
            try:
                with open(file_path, mode='r', encoding=enc) as f:
                    content = f.readlines()
                break
            except Exception:
                continue
                
        if not content:
            return []
            
        reader = csv.DictReader(content)
        for row in reader:
            raw_date = row.get("Data", "").strip()
            lancamento = row.get("Lançamento", "").strip()
            detalhes = row.get("Detalhes", "").strip()
            num_doc = row.get("N° documento", "").strip()
            raw_valor = row.get("Valor", "").strip()
            tipo_lancamento = row.get("Tipo Lançamento", "").strip()
            
            if not tipo_lancamento or not raw_valor:
                continue
            if "saldo" in lancamento.lower():
                continue
                
            try:
                dt = datetime.strptime(raw_date, "%d/%m/%Y")
                data_iso = dt.strftime("%Y-%m-%d")
            except Exception:
                data_iso = raw_date
                
            val_clean = raw_valor.replace("-", "").strip()
            valor = clean_br_number(val_clean)
            
            detalhe_limpo = re.sub(r"^\d{2}/\d{2}\s+\d{2}:\d{2}\s+", "", detalhes).strip()
            
            # Detecta se é transferência automática da Conta Salário BB
            if tipo_lancamento == "Entrada" and "transferência recebida" in lancamento.lower():
                descricao = "Salário Líquido Recebido (Conta Salário BB)"
                cat = "Salário & Proventos"
                tipo = "Receita"
            else:
                if detalhe_limpo and detalhe_limpo != lancamento:
                    descricao = f"{detalhe_limpo} ({lancamento})"
                    busca_cat = f"{detalhe_limpo} {lancamento}"
                else:
                    descricao = lancamento
                    busca_cat = lancamento
                    
                cat, tipo = categorize(busca_cat, original_tipo=tipo_lancamento, user_rules=user_rules)
                
                if tipo_lancamento == "Entrada" and tipo not in ("Receita", "Transferência / Fatura"):
                    tipo = "Receita"
                    cat = "Outras Receitas"
                
            t = Transaction(
                data=data_iso,
                banco="Banco do Brasil",
                conta_tipo="Conta Corrente",
                descricao=descricao,
                valor=valor,
                tipo_movimentacao=tipo,
                categoria=cat,
                documento=num_doc,
                arquivo_origem=file_path
            )
            t.id = t.generate_id()
            transactions.append(t)
            
        return transactions
