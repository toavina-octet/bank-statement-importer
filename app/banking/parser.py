from __future__ import annotations

import re
from abc import ABC, abstractmethod
from datetime import datetime
from decimal import Decimal

from app.banking.models import StatementData, Transaction


class ParsingError(Exception):
    """Raised when parsing fails."""


class BaseParser(ABC):
    @abstractmethod
    def parse(self, text: str) -> StatementData:
        """Parse the extracted text into StatementData."""


class GenericParser(BaseParser):
    """
    A generic parser that uses regular expressions to find typical bank statement patterns.
    This is a fallback/template that should be refined for specific banks.
    """

    def parse(self, text: str) -> StatementData:
        if BniStatementParser.matches(text):
            return BniStatementParser().parse(text)

        try:
            account_number = self._extract_account_number(text)
            statement_date = self._extract_date(text)
            old_balance = self._extract_balance(text, "ancien")
            new_balance = self._extract_balance(text, "nouveau")
            transactions = self._extract_transactions(text)

            return StatementData(
                account_number=account_number,
                statement_date=statement_date,
                old_balance=old_balance,
                new_balance=new_balance,
                transactions=tuple(transactions),
            )
        except Exception as exc:
            raise ParsingError(f"Generic parsing failed: {exc}") from exc

    def _extract_account_number(self, text: str) -> str:
        # Look for IBAN or typical account number patterns
        match = re.search(r"FR\d{2}([\s-]?[\dA-Z]){10,32}", text)
        if match:
            return re.sub(r"[\s-]+", "", match.group(0))
        return "UNKNOWN"

    def _extract_date(self, text: str) -> datetime.date:
        # Look for dates like DD/MM/YYYY or DD.MM.YYYY
        match = re.search(r"(\d{2}[/.]\d{2}[/.]\d{4})", text)
        if match:
            return datetime.strptime(match.group(1).replace(".", "/"), "%d/%m/%Y").date()
        return datetime.now().date()

    def _extract_balance(self, text: str, type_hint: str) -> Decimal:
        # Search for lines containing balance keywords
        pattern = rf"{type_hint}.*?([\d\s]+[.,]\d{{2}})"
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            val = match.group(1).replace(" ", "").replace(",", ".")
            return Decimal(val)
        return Decimal("0.00")

    def _extract_transactions(self, text: str) -> list[Transaction]:
        # This is the hardest part without specific formats.
        # We'll look for lines with a date and an amount.
        transactions = []
        # Pattern: Date (DD/MM) + Label + Amount (-XXX,XX)
        lines = text.splitlines()
        for line in lines:
            line = line.strip()
            match = re.search(r"(\d{2}/\d{2})\s+(.*?)\s+(-?[\d\s]+[.,]\d{2})$", line)
            if match:
                label = match.group(2).strip()
                amount_str = match.group(3).replace(" ", "").replace(",", ".")
                amount = Decimal(amount_str)

                # In a real scenario, we'd need to determine if it's credit or debit.
                # Here we use the sign if present, otherwise assume credit for simplicity.
                transactions.append(
                    
                    Transaction(
                        date=datetime.now().date(),  # Year is usually missing in lines
                        label=label,
                        amount=amount.copy_abs(),
                        is_credit=amount >= 0,
                    )
                )
        return transactions


class BniStatementParser(BaseParser):
    """Parser for BNI Madagascar account statement PDFs."""

    _amount_pattern = r"\d{1,3}(?:\.\d{3})*,\d{2}"
    _debit_prefixes = ("PR", "CR", "VB", "VS", "PC")
    _credit_prefixes = ("VA", "VR")
    _debit_keywords = (
        "PRELEVEMENT",
        "PAIEMENT CHEQUE",
        "RETRAIT",
        "COMMISSION",
        "IMPOT",
        "FRAIS SUR VIREMENT",
        "FACTURE",
        "FCT",
    )
    _credit_keywords = ("BCN VIRT", "VIREMENT", "VERSEMENT")

    @classmethod
    def matches(cls, text: str) -> bool:
        normalized = text.upper()
        return "RELEVE DE COMPTE" in normalized and "BNI" in normalized

    def parse(self, text: str) -> StatementData:
        try:
            lines = [line.strip() for line in text.splitlines() if line.strip()]
            account_number = self._extract_account_number(text)
            statement_date = self._extract_statement_end_date(text)
            old_balance = self._extract_named_balance(text, "Ancien solde")
            new_balance = self._extract_named_balance(text, "Nouveau solde")
            transactions = self._extract_transactions(lines, statement_date.year)

            return StatementData(
                account_number=account_number,
                statement_date=statement_date,
                old_balance=old_balance,
                new_balance=new_balance,
                transactions=tuple(transactions),
            )
        except Exception as exc:
            raise ParsingError(f"BNI parsing failed: {exc}") from exc

    def _extract_account_number(self, text: str) -> str:
        match = re.search(r"Compte\s+N[°º]\s+([0-9-]+)", text, re.IGNORECASE)
        if match:
            return match.group(1)

        iban_match = re.search(r"IBAN\s+MG\d{2}\s+\d{5}\s+\d{5}\s+(\d+)\s+(\d{2})", text)
        if iban_match:
            return f"{iban_match.group(1)}-{iban_match.group(2)}"

        raise ParsingError("account number not found")

    def _extract_statement_end_date(self, text: str) -> datetime.date:
        match = re.search(r"du\s+\d{2}/\d{2}/\d{4}\s+au\s+(\d{2}/\d{2}/\d{4})", text)
        if match:
            return datetime.strptime(match.group(1), "%d/%m/%Y").date()

        match = re.search(r"Nouveau solde au\s+(\d{2}/\d{2}/\d{4})", text, re.IGNORECASE)
        if match:
            return datetime.strptime(match.group(1), "%d/%m/%Y").date()

        raise ParsingError("statement end date not found")

    def _extract_named_balance(self, text: str, label: str) -> Decimal:
        pattern = rf"{label}\s+au\s+\d{{2}}/\d{{2}}/\d{{4}}\s+({self._amount_pattern})"
        match = re.search(pattern, text, re.IGNORECASE)
        if not match:
            raise ParsingError(f"{label.lower()} not found")
        return _parse_localized_decimal(match.group(1))

    def _extract_transactions(self, lines: list[str], statement_year: int) -> list[Transaction]:
        transactions: list[Transaction] = []
        current_index: int | None = None

        row_pattern = re.compile(
            rf"^([A-Z]{{2}}\d+)\s+"
            rf"(\d{{2}}/\d{{2}}/\d{{2}})\s+"
            rf"(.+?)\s+"
            rf"(\d{{2}}/\d{{2}}/\d{{2}})\s+"
            rf"(?:(?P<debit>{self._amount_pattern})\s+(?P<credit>{self._amount_pattern})(?:\s+{self._amount_pattern})?|(?P<amount>{self._amount_pattern})(?:\s+{self._amount_pattern})?)$",
            re.IGNORECASE,
        )

        for line in lines:
            match = row_pattern.match(line)
            if not match:
                if current_index is not None and not self._is_statement_noise(line):
                    current = transactions[current_index]
                    transactions[current_index] = Transaction(
                        date=current.date,
                        label=f"{current.label} {line}".strip(),
                        amount=current.amount,
                        is_credit=current.is_credit,
                    )
                continue

            operation_code = match.group(1)
            operation_date = match.group(2)
            label = match.group(3)
            amount = match.group("amount")
            debit_amount = match.group("debit")
            credit_amount = match.group("credit")

            if debit_amount or credit_amount:
                if credit_amount and not debit_amount:
                    transaction_amount = _parse_localized_decimal(credit_amount)
                    is_credit = True
                elif debit_amount and not credit_amount:
                    transaction_amount = _parse_localized_decimal(debit_amount)
                    is_credit = False
                else:
                    transaction_amount = _parse_localized_decimal(credit_amount or debit_amount)
                    is_credit = self._is_credit_operation(operation_code, label)
            elif amount:
                transaction_amount = _parse_localized_decimal(amount)
                is_credit = self._is_credit_operation(operation_code, label)
            else:
                raise ParsingError(f"transaction amount not found for line: {line}")

            transaction = Transaction(
                date=self._parse_short_date(operation_date, statement_year),
                label=label.strip(),
                amount=transaction_amount,
                is_credit=is_credit,
            )
            transactions.append(transaction)
            current_index = len(transactions) - 1

        return transactions

    def _parse_short_date(self, value: str, statement_year: int) -> datetime.date:
        parsed = datetime.strptime(value, "%d/%m/%y").date()
        return parsed.replace(year=statement_year)

    def _is_credit_operation(self, operation_code: str, label: str) -> bool:
        normalized_label = label.upper()

        if operation_code.startswith(self._debit_prefixes):
            return False

        if operation_code.startswith(self._credit_prefixes):
            return True

        if any(keyword in normalized_label for keyword in self._debit_keywords):
            return False

        if any(keyword in normalized_label for keyword in self._credit_keywords):
            return True

        raise ParsingError(
            f"cannot determine debit/credit column for {operation_code}: {label}"
        )

    def _is_statement_noise(self, line: str) -> bool:
        normalized = line.upper()
        return (
            normalized.startswith("NOUVEAU SOLDE")
            or normalized.startswith("ANCIEN SOLDE")
            or normalized == "CRÉDIT"
            or normalized == "CREDIT"
            or normalized.startswith("SEUL CE RELEV")
            or normalized.startswith("ADRESSE:")
            or normalized.startswith("BNI MADAGASCAR")
            or normalized.startswith("FINANCIERS")
        )


def _parse_localized_decimal(value: str) -> Decimal:
    return Decimal(value.replace(".", "").replace(" ", "").replace(",", "."))
