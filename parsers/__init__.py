import os
import glob
from typing import List, Dict
from .base import Transaction
from .nubank import NubankParser
from .bb import BancoDoBrasilParser
from .atacadao import AtacadaoParser
from .mercadopago import MercadoPagoParser
from .caixa import CaixaParser
from .boleto import BoletoParser
from .salario import SalarioParser
from .inter import BancoInterParser
import database

def detect_and_parse(file_path: str, passwords: List[str] = None, user_rules: dict = None) -> List[Transaction]:
    """
    Detecta automaticamente o formato do arquivo e extrai as transações.
    """
    path_lower = file_path.lower()
    passwords = passwords or [""]
    
    # 1. Detecção por pasta
    if "nubank" in path_lower:
        if file_path.endswith(".csv"):
            return NubankParser.parse(file_path, user_rules=user_rules)
    elif "inter" in path_lower:
        if file_path.endswith(".pdf"):
            return BancoInterParser.parse(file_path, passwords=passwords, user_rules=user_rules)
    elif "banco do brasil" in path_lower or "/bb/" in path_lower:
        if file_path.endswith(".csv"):
            return BancoDoBrasilParser.parse(file_path, user_rules=user_rules)
    elif "salario" in path_lower or "contracheque" in path_lower or "demonstrativo" in path_lower:
        if file_path.endswith(".pdf"):
            txs, meta = SalarioParser.parse_full(file_path, user_rules=user_rules)
            if meta:
                database.save_contracheque(meta)
            return txs
    elif "atacadao" in path_lower:
        if file_path.endswith(".pdf"):
            return AtacadaoParser.parse(file_path, passwords=passwords, user_rules=user_rules)
    elif "caixa" in path_lower:
        if file_path.endswith(".pdf"):
            return CaixaParser.parse(file_path, user_rules=user_rules)
    elif "mercado pago" in path_lower or "mercadopago" in path_lower:
        if file_path.endswith(".pdf"):
            return MercadoPagoParser.parse(file_path, user_rules=user_rules)

    # 2. Detecção por conteúdo do arquivo caso o caminho não seja específico
    if file_path.endswith(".csv"):
        try:
            with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                head = f.read(1024)
            if "date,title,amount" in head:
                return NubankParser.parse(file_path, user_rules=user_rules)
            elif "Tipo Lançamento" in head or "Lançamento" in head or "Extrato conta corrente" in file_path:
                return BancoDoBrasilParser.parse(file_path, user_rules=user_rules)
        except Exception:
            pass

    if file_path.endswith(".pdf"):
        # Tenta Demonstrativo de Pagamento (Salário)
        try:
            txs, meta = SalarioParser.parse_full(file_path, user_rules=user_rules)
            if txs and meta:
                database.save_contracheque(meta)
                return txs
        except Exception:
            pass

        # Tenta Atacadão (se precisar de senha)
        try:
            ts = AtacadaoParser.parse(file_path, passwords=passwords, user_rules=user_rules)
            if ts:
                return ts
        except Exception:
            pass
            
        # Tenta Mercado Pago
        try:
            ts = MercadoPagoParser.parse(file_path, user_rules=user_rules)
            if ts:
                return ts
        except Exception:
            pass
            
        # Tenta Boleto
        try:
            ts = BoletoParser.parse(file_path, user_rules=user_rules)
            if ts:
                return ts
        except Exception:
            pass
            
        # Tenta Caixa por OCR
        try:
            ts = CaixaParser.parse(file_path, user_rules=user_rules)
            if ts:
                return ts
        except Exception:
            pass

    return []

def scan_and_ingest_all(base_folder: str = "dados", force_reload: bool = False, passwords: List[str] = None) -> Dict:
    """
    Varre a pasta base e processa arquivos novos ou alterados, inserindo no banco SQLite
    e executando a reconciliação de salários e benefícios mensais fixos (VA e VT).
    """
    database.init_db()
    
    saved_pw = database.get_config("pdf_passwords", "")
    active_passwords = list(set((passwords or []) + [p.strip() for p in saved_pw.split(",") if p.strip()] + [""]))
    
    user_rules = database.get_user_rules()
    
    report = {
        "arquivos_verificados": 0,
        "arquivos_novos": 0,
        "transacoes_inseridas": 0,
        "erros": []
    }
    
    patterns = [
        os.path.join(base_folder, "**", "*.csv"),
        os.path.join(base_folder, "**", "*.pdf")
    ]
    
    all_files = []
    for pat in patterns:
        all_files.extend(glob.glob(pat, recursive=True))
        
    all_files = sorted(list(set(all_files)))
    report["arquivos_verificados"] = len(all_files)
    
    for fpath in all_files:
        try:
            stat = os.stat(fpath)
            mtime = stat.st_mtime
            size = stat.st_size
            
            if not force_reload and database.is_file_processed(fpath, mtime, size):
                continue
                
            report["arquivos_novos"] += 1
            print(f"[Ingestão] Processando: {fpath}...")
            
            txs = detect_and_parse(fpath, passwords=active_passwords, user_rules=user_rules)
            inserted = database.save_transactions(txs)
            report["transacoes_inseridas"] += inserted
            
            database.mark_file_processed(fpath, mtime, size, len(txs), status="OK")
            print(f"[Ingestão] Concluído: {fpath} ({len(txs)} encontradas, {inserted} novas inseridas)")
        except Exception as e:
            report["erros"].append(f"{fpath}: {str(e)}")
            print(f"[Ingestão] Erro em {fpath}: {e}")

    # Reconcilia salários (BB vs Contracheque) e garante benefícios fixos mensais (VA e VT no dia 01)
    database.reconcile_salaries_and_benefits()
            
    return report
