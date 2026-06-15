from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from app.banking.models import StatementData, Transaction
from app.banking.validator import CoherenceError, validate_statement_coherence


def test_validate_statement_coherence_success() -> None:
    data = StatementData(
        account_number="12345",
        statement_date=date(2026, 6, 1),
        old_balance=Decimal("1000.00"),
        new_balance=Decimal("1050.00"),
        transactions=(
            Transaction(
                date=date(2026, 6, 2), label="Credit", amount=Decimal("100.00"), is_credit=True
            ),
            Transaction(
                date=date(2026, 6, 3), label="Debit", amount=Decimal("50.00"), is_credit=False
            ),
        ),
    )

    # Should not raise
    validate_statement_coherence(data)


def test_validate_statement_coherence_failure() -> None:
    data = StatementData(
        account_number="12345",
        statement_date=date(2026, 6, 1),
        old_balance=Decimal("1000.00"),
        new_balance=Decimal("1100.00"),  # Wrong balance (should be 1050)
        transactions=(
            Transaction(
                date=date(2026, 6, 2), label="Credit", amount=Decimal("100.00"), is_credit=True
            ),
            Transaction(
                date=date(2026, 6, 3), label="Debit", amount=Decimal("50.00"), is_credit=False
            ),
        ),
    )

    with pytest.raises(CoherenceError) as excinfo:
        validate_statement_coherence(data)

    assert excinfo.value.expected == Decimal("1050.00")
    assert excinfo.value.actual == Decimal("1100.00")
