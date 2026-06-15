from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal


@dataclass(frozen=True)
class Transaction:
    date: date
    label: str
    amount: Decimal
    is_credit: bool

    @property
    def signed_amount(self) -> Decimal:
        return self.amount if self.is_credit else -self.amount


@dataclass(frozen=True)
class StatementData:
    account_number: str
    statement_date: date
    old_balance: Decimal
    new_balance: Decimal
    transactions: tuple[Transaction, ...]

    def calculate_expected_balance(self) -> Decimal:
        return self.old_balance + sum(t.signed_amount for t in self.transactions)

    def is_coherent(self) -> bool:
        return self.calculate_expected_balance() == self.new_balance
