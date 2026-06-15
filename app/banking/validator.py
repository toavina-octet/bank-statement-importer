from __future__ import annotations

import logging
from decimal import Decimal

from app.banking.models import StatementData

logger = logging.getLogger(__name__)


class CoherenceError(Exception):
    """Raised when statement data is not coherent."""

    def __init__(self, expected: Decimal, actual: Decimal) -> None:
        super().__init__(f"Balance mismatch: expected {expected}, got {actual}")
        self.expected = expected
        self.actual = actual


def validate_statement_coherence(data: StatementData) -> None:
    """
    Validate that the statement data is coherent.
    Règle : ancien solde + crédits - débits = nouveau solde
    """
    expected = data.calculate_expected_balance()
    if expected != data.new_balance:
        logger.error(
            "Coherence check failed for account %s: expected balance %s != actual %s",
            data.account_number,
            expected,
            data.new_balance,
        )
        raise CoherenceError(expected=expected, actual=data.new_balance)

    logger.info(
        "Coherence check passed for account %s: balance %s",
        data.account_number,
        data.new_balance,
    )
