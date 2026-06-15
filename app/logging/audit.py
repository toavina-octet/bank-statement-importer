from __future__ import annotations

import logging
from typing import Any


class AuditLogger:
    def __init__(self, name: str = "bank_importer.audit") -> None:
        self._logger = logging.getLogger(name)

    def log_connection_success(self, provider: str) -> None:
        self._logger.info("Connection successful: provider=%s", provider)

    def log_connection_failure(self, provider: str, error: Exception) -> None:
        self._logger.error(
            "Connection failed: provider=%s error=%s",
            provider,
            str(error),
        )

    def log_import_success(self, client: str) -> None:
        self._logger.info("Import successful: client=%s", client)

    def log_import_rejected(self, client: str, reason: str, details: dict[str, Any]) -> None:
        self._logger.warning(
            "Import rejected: client=%s reason=%s error=%s",
            client,
            reason,
            details.get("error", ""),
        )

    def log_duplicate_detected(self, client: str, hash_val: str) -> None:
        self._logger.info(
            "Duplicate detected: client=%s hash=%s",
            client,
            hash_val,
        )

    def log_technical_error(self, context: str, error: Exception) -> None:
        self._logger.exception("Technical error in %s: %s", context, str(error))


audit_logger = AuditLogger()
