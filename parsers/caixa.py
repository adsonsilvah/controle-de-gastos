import re
from datetime import datetime
from typing import List
from pypdf import PdfReader
from rapidocr_onnxruntime import RapidOCR
from .base import Transaction
from categorizer import categorize

def clean_br_number(val: str) -> float:
    s = str(val).strip().replace("R$", "").replace("RS", "").replace(" ", "").replace(".", "")
    s = s.replace(",", ".").replace("-", "")
    return float(s)

class CaixaParser:
    _ocr_engine = None

    @classmethod
    def get_ocr(cls):
        if cls._ocr_engine is None:
            cls._ocr_engine = RapidOCR()
        return cls._ocr_engine

    @classmethod
    def parse(cls, file_path: str, user_rules: dict = None) -> List[Transaction]:
        transactions = []
        try:
            reader = PdfReader(file_path)
            engine = cls.get_ocr()
            
            for page in reader.pages:
                for img in page.images:
                    res, _ = engine(img.data)
                    if not res:
                        continue
                    page_txs = cls._parse_ocr_items(res, file_path, user_rules)
                    transactions.extend(page_txs)
        except Exception as e:
            print(f"[Caixa] Erro ao processar {file_path}: {e}")
            
        return transactions

    @staticmethod
    def _parse_ocr_items(ocr_items: list, file_path: str, user_rules: dict = None) -> List[Transaction]:
        """
        Agrupa os itens do OCR pela coordenada vertical (y) formando as linhas exatas da tabela,
        e separa as colunas pela coordenada horizontal (x):
          - x < 250: Data e Hora (DD/MM/YYYY-HH:MM:SS)
          - 250 <= x < 420: Nr. Doc
          - 420 <= x < 950: Histórico / Complemento
          - 950 <= x < 1260: Favorecido
          - 1400 <= x < 1620: Valor da Transação (ex: 18,52 D)
          - x >= 1620: Saldo Acumulado (ignorado)
        """
        txs = []
        date_regex = re.compile(r"(\d{2}/\d{2}/\d{4})[-\s]*(\d{2}:\d{2}:\d{2})")
        val_regex = re.compile(r"^([\d\.,]+)\s*([CD])$")

        # 1. Encontra todas as âncoras de data/hora de transação (exceto 00:00:00 que é SALDO DIA)
        anchors = []
        for box, text, _ in ocr_items:
            txt = text.strip()
            m = date_regex.search(txt)
            if m and m.group(2) != "00:00:00":
                y_center = (box[0][1] + box[2][1]) / 2.0
                anchors.append((y_center, m.group(1), m.group(2)))

        for y_row, data_dm, hora in anchors:
            try:
                dt = datetime.strptime(data_dm, "%d/%m/%Y")
                data_iso = dt.strftime("%Y-%m-%d")
            except Exception:
                data_iso = data_dm

            nr_doc = ""
            historico = []
            favorecido = []
            valor = 0.0
            indicator = "D"

            # Busca todos os elementos na mesma linha horizontal (tolerância de ±22 pixels em y)
            for box, text, _ in ocr_items:
                y_item = (box[0][1] + box[2][1]) / 2.0
                if abs(y_item - y_row) <= 22:
                    x0 = box[0][0]
                    txt = text.strip()
                    if not txt or date_regex.search(txt):
                        continue

                    if 250 <= x0 < 420:
                        nr_doc = txt
                    elif 420 <= x0 < 950:
                        if "SALDO" not in txt.upper():
                            historico.append(txt)
                    elif 950 <= x0 < 1260:
                        if "SALDO" not in txt.upper():
                            favorecido.append(txt)
                    elif 1380 <= x0 < 1620:
                        vm = val_regex.match(txt)
                        if vm:
                            valor = clean_br_number(vm.group(1))
                            indicator = vm.group(2)

            if valor <= 0:
                continue

            hist_str = " ".join(historico).strip()
            fav_str = " ".join(favorecido).strip()

            if fav_str and hist_str:
                descricao = f"{fav_str} ({hist_str})"
                busca_cat = f"{fav_str} {hist_str}"
            elif fav_str:
                descricao = fav_str
                busca_cat = fav_str
            elif hist_str:
                descricao = hist_str
                busca_cat = hist_str
            else:
                descricao = "Movimentação Caixa"
                busca_cat = descricao

            tipo_banco = "Entrada" if indicator == "C" else "Saída"
            cat, tipo = categorize(busca_cat, original_tipo=tipo_banco, user_rules=user_rules)

            # Devolução de Pix ou Crédito explícito
            if indicator == "C" and tipo == "Despesa":
                if "devolucao" in busca_cat.lower() or "estorno" in busca_cat.lower():
                    tipo = "Receita"
                    cat = "Estornos & Devoluções"
                else:
                    tipo = "Receita"
                    cat = "Outras Receitas"

            t = Transaction(
                data=data_iso,
                banco="Caixa Econômica",
                conta_tipo="Conta Corrente",
                descricao=descricao,
                valor=valor,
                tipo_movimentacao=tipo,
                categoria=cat,
                documento=f"{nr_doc} {hora}".strip(),
                arquivo_origem=file_path
            )
            t.id = t.generate_id()
            txs.append(t)

        return txs
