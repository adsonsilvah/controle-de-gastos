import re
from datetime import datetime, timedelta
from typing import Optional, List
import pdfplumber
from .base import Transaction
from categorizer import categorize

# Data base FEBRABAN para fator de vencimento (07/10/1997)
FEBRABAN_BASE = datetime(1997, 10, 7)

def decode_linha_digitavel(linha: str) -> Optional[dict]:
    """
    Decodifica linha digitável de boleto bancário padrão (47 dígitos)
    Formato: AAABC.CCCCX DDDDD.DDDDDY EEEEE.EEEEEZ K UUUUVVVVVVVVVV
    """
    numeros = re.sub(r"\D", "", linha)
    if len(numeros) != 47:
        return None
        
    banco_cod = numeros[0:3]
    fator_venc = int(numeros[33:37])
    valor_cents = int(numeros[37:47])
    valor = valor_cents / 100.0
    
    # Cálculo da data de vencimento
    data_venc = None
    if fator_venc > 0:
        # Após 10000 dias (21/02/2025), o fator reinicia em 1000
        if fator_venc >= 1000 and datetime.now().year >= 2025:
            # Novo ciclo febraban
            base_novo_ciclo = datetime(2025, 2, 22)
            data_venc = base_novo_ciclo + timedelta(days=(fator_venc - 1000))
        else:
            data_venc = FEBRABAN_BASE + timedelta(days=fator_venc)
            
    return {
        "banco_codigo": banco_cod,
        "vencimento": data_venc.strftime("%Y-%m-%d") if data_venc else None,
        "valor": valor,
        "linha": linha
    }

class BoletoParser:
    @staticmethod
    def parse(file_path: str, user_rules: dict = None) -> List[Transaction]:
        transactions = []
        try:
            with pdfplumber.open(file_path) as pdf:
                full_text = "\n".join([p.extract_text() or "" for p in pdf.pages])
                
                # Procura linha digitável: 5 blocos numéricos
                # ex: 23793.38128 60000.000003 00000.000003 1 90000000000000
                m_linha = re.search(r"\b(\d{5}[\.\s]?\d{5}\s+\d{5}[\.\s]?\d{6}\s+\d{5}[\.\s]?\d{6}\s+\d\s+\d{14})\b", full_text)
                if not m_linha:
                    # Tenta sequência direta de 47 dígitos
                    m_linha = re.search(r"\b(\d{47})\b", full_text)
                    
                if m_linha:
                    info = decode_linha_digitavel(m_linha.group(1))
                    if info:
                        # Extrai beneficiário se possível
                        beneficiario = "Boleto a Pagar"
                        m_benef = re.search(r"(?:Benefici[áa]rio|Cedente)[:\s]+([^\n\r]+)", full_text, re.IGNORECASE)
                        if m_benef:
                            beneficiario = m_benef.group(1).strip()[:60]
                            
                        cat, tipo = categorize(beneficiario, original_tipo="Saída", user_rules=user_rules)
                        
                        t = Transaction(
                            data=info["vencimento"] or datetime.now().strftime("%Y-%m-%d"),
                            banco="Boleto",
                            conta_tipo="Boleto",
                            descricao=f"Boleto: {beneficiario}",
                            valor=info["valor"],
                            tipo_movimentacao="Despesa",
                            categoria=cat,
                            documento=m_linha.group(1)[:20],
                            arquivo_origem=file_path
                        )
                        t.id = t.generate_id()
                        transactions.append(t)
        except Exception as e:
            print(f"[Boleto] Erro ao ler {file_path}: {e}")
            
        return transactions
