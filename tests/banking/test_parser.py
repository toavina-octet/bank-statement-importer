from __future__ import annotations

from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from app.banking.parser import GenericParser
from app.banking.validator import validate_statement_coherence
from app.pdf.extractor import PdfExtractor


def test_generic_parser_extracts_data() -> None:
    sample_text = """
    RELEVE DE COMPTE
    IBAN: FR76 30001 00700 00012345678 90
    Date du relevé: 01/06/2026
    
    Ancien solde au 01/05/2026: 1 000,00 EUR
    
    MOUVEMENTS:
    15/05 VIREMENT RECU SALAIRE 2 500,00
    20/05 LOYER -800,00
    25/05 COURSES -150,00
    
    Nouveau solde au 01/06/2026: 2 550,00 EUR
    """
    
    parser = GenericParser()
    data = parser.parse(sample_text)
    
    assert data.account_number == "FR7630001007000001234567890"
    assert data.statement_date == date(2026, 6, 1)
    assert data.old_balance == Decimal("1000.00")
    assert data.new_balance == Decimal("2550.00")
    
    assert len(data.transactions) == 3
    assert data.transactions[0].label == "VIREMENT RECU SALAIRE"
    assert data.transactions[0].amount == Decimal("2500.00")
    assert data.transactions[0].is_credit is True
    
    assert data.transactions[1].label == "LOYER"
    assert data.transactions[1].amount == Decimal("800.00")
    assert data.transactions[1].is_credit is False


@pytest.mark.parametrize(
    ("filename", "account_number", "statement_date", "old_balance", "new_balance", "tx_count"),
    [
        (
            "Releves_J_27234520100-79_04062026_05062026_3719.pdf",
            "27234520100-79",
            date(2026, 6, 5),
            Decimal("248229319.04"),
            Decimal("244294193.04"),
            3,
        ),
        (
            "Releves_J_27234520100-79_05062026_08062026_176.pdf",
            "27234520100-79",
            date(2026, 6, 8),
            Decimal("244294193.04"),
            Decimal("250404420.47"),
            4,
        ),
        (
            "Releves_J_27234520161-90_04062026_05062026_3718.pdf",
            "27234520161-90",
            date(2026, 6, 5),
            Decimal("10697.89"),
            Decimal("10697.89"),
            0,
        ),
        (
            "Releves_J_27234520161-90_05062026_08062026_175.pdf",
            "27234520161-90",
            date(2026, 6, 8),
            Decimal("10697.89"),
            Decimal("10697.89"),
            0,
        ),
    ],
)
def test_bni_releve_pdfs_are_parsed_and_coherent(
    filename: str,
    account_number: str,
    statement_date: date,
    old_balance: Decimal,
    new_balance: Decimal,
    tx_count: int,
) -> None:
    pdf_path = Path("releves") / filename
    if not pdf_path.exists():
        pytest.skip(f"Sample statement is missing: {pdf_path}")

    text = PdfExtractor().extract_text(pdf_path)
    data = GenericParser().parse(text)

    validate_statement_coherence(data)
    assert data.account_number == account_number
    assert data.statement_date == statement_date
    assert data.old_balance == old_balance
    assert data.new_balance == new_balance
    assert len(data.transactions) == tx_count


def test_bni_releve_extracts_debits_and_credits() -> None:
    pdf_path = Path("releves/Releves_J_27234520100-79_05062026_08062026_176.pdf")
    if not pdf_path.exists():
        pytest.skip(f"Sample statement is missing: {pdf_path}")

    data = GenericParser().parse(PdfExtractor().extract_text(pdf_path))

    assert [transaction.is_credit for transaction in data.transactions] == [
        True,
        True,
        False,
        False,
    ]
    assert [transaction.amount for transaction in data.transactions] == [
        Decimal("1884394.80"),
        Decimal("5038535.83"),
        Decimal("484700.00"),
        Decimal("328003.20"),
    ]


def test_bni_parser_classifies_vb_vs_as_debit() -> None:
    sample_text = """
    RELEVE DE COMPTE
    BNI MADAGASCAR
    Compte N° 27234520100-79
    du 01/06/2026 au 02/06/2026
    Ancien solde au 01/06/2026 376.084.691,54
    Pièce Date Nature de l'opération Valeur Débit Crédit
    VB700005176 02/06/26 BCN VIREMENT AUTRE BANQUE 01/06/26 1.200.000,00
    VB700005177 02/06/26 BCN VIREMENT AUTRE BANQUE 01/06/26 1.200.000,00
    VA900022449 02/06/26 VIREMENT 02/06/26 11.106.941,08
    VS700003138 02/06/26 BCN VIRT AUTRE AGENCE 01/06/26 5.257.412,78
    RC622136 02/06/26 PAIEMENT CHEQUE 01/06/26 100.000.000,00
    VS700003136 02/06/26 BCN VIRT AUTRE AGENCE 01/06/26 5.865.586,00
    VS700003137 02/06/26 BCN VIRT AUTRE AGENCE 01/06/26 24.667.631,22
    Nouveau solde au 02/06/2026 249.001.002,62
    """

    data = GenericParser().parse(sample_text)

    assert [transaction.is_credit for transaction in data.transactions] == [
        False,
        False,
        True,
        False,
        False,
        False,
        False,
    ]


def test_bni_parser_treats_pc_as_debit() -> None:
    sample_text = """
    RELEVE DE COMPTE
    BNI MADAGASCAR
    Compte N° 27234520100-79
    du 01/06/2026 au 02/06/2026
    Ancien solde au 01/06/2026 100.000,00
    Pièce Date Nature de l'opération Valeur Débit Crédit
    PC260605821 02/06/26 FCT SIT-26-0153 SIT PALA 01062 01/06/26 50.000,00
    Nouveau solde au 02/06/2026 50.000,00
    """

    data = GenericParser().parse(sample_text)

    assert len(data.transactions) == 1
    assert data.transactions[0].label == "FCT SIT-26-0153 SIT PALA 01062"
    assert data.transactions[0].is_credit is False
