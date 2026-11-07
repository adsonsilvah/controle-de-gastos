from dataclasses import dataclass, asdict
from typing import Optional
import hashlib

@dataclass
class Transaction:
    data: str                      # YYYY-MM-DD
    banco: str                     # ex: 'Nubank', 'Banco do Brasil', 'Atacadão', 'Caixa', 'Mercado Pago'
    conta_tipo: str                # 'Cartão de Crédito' ou 'Conta Corrente'
    descricao: str                 # Nome do estabelecimento / favorecido / histórico
    valor: float                   # Valor monetário (positivo)
    tipo_movimentacao: str         # 'Despesa', 'Receita' ou 'Transferência / Fatura'
    categoria: str                 # Categoria atribuída automaticamente ou pelo usuário
    documento: Optional[str] = ""  # ID da transação ou número do documento
    arquivo_origem: Optional[str] = ""
    id: Optional[str] = ""         # Hash único para deduplicação

    def generate_id(self) -> str:
        # Gera hash estável para evitar duplicidade de importação
        raw = f"{self.banco}|{self.conta_tipo}|{self.data}|{self.descricao}|{self.valor:.2f}|{self.documento}|{self.tipo_movimentacao}"
        return hashlib.sha256(raw.encode('utf-8')).hexdigest()

    def to_dict(self):
        d = asdict(self)
        if not d.get("id"):
            d["id"] = self.generate_id()
        return d
