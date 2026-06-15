from __future__ import annotations

import logging
import os
import sys
import time
from dataclasses import asdict, dataclass
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

from app.banking.parser import GenericParser
from app.config import ConfigurationError, load_clients_config
from app.config.models import ClientConfig
from app.database import create_database_engine, create_session_factory, initialize_database
from app.importer import StatementImportService
from app.logging.audit import audit_logger
from app.mail import ImapStatementCollector, MailCredentials
from app.odoo.client import OdooClient


def _env_int(name: str, default: int) -> int:
    value = os.getenv(name)
    if value is None:
        return default
    try:
        return int(value)
    except ValueError:
        return default


def configure_logging() -> None:
    level_name = os.getenv("LOG_LEVEL", "INFO").upper()
    level = getattr(logging, level_name, logging.INFO)
    logs_dir = Path(os.getenv("LOGS_DIR", "./logs"))
    log_file = os.getenv("LOG_FILE", "bank_importer.log")
    max_bytes = _env_int("LOG_MAX_BYTES", 10 * 1024 * 1024)
    backup_count = _env_int("LOG_BACKUP_COUNT", 5)

    logs_dir.mkdir(parents=True, exist_ok=True)
    formatter = logging.Formatter("%(asctime)s %(levelname)s [%(name)s] %(message)s")

    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)

    file_handler = RotatingFileHandler(
        logs_dir / log_file,
        maxBytes=max_bytes,
        backupCount=backup_count,
        encoding="utf-8",
    )
    file_handler.setFormatter(formatter)

    logging.basicConfig(
        level=level,
        handlers=[console_handler, file_handler],
        force=True,
    )


def _mail_credentials_for_client(client: ClientConfig) -> MailCredentials:
    return MailCredentials(
        host=client.mailbox.host,
        port=client.mailbox.port,
        username=client.mailbox.username,
        password=client.mailbox.get_password(os.environ),
        use_ssl=client.mailbox.use_ssl,
        folder=client.mailbox.folder,
    )


@dataclass(frozen=True)
class BatchImportSummary:
    requested_client_slug: str | None
    processed_clients: int
    imported_documents: int
    duplicate_documents: int
    rejected_messages: int
    client_summaries: tuple[Any, ...]

    def as_dict(self) -> dict[str, Any]:
        return {
            "requested_client_slug": self.requested_client_slug,
            "processed_clients": self.processed_clients,
            "imported_documents": self.imported_documents,
            "duplicate_documents": self.duplicate_documents,
            "rejected_messages": self.rejected_messages,
            "client_summaries": [asdict(summary) for summary in self.client_summaries],
        }


def run_import_once(client_slug: str | None = None) -> BatchImportSummary:
    logger = logging.getLogger("bank_importer")

    data_dir = Path(os.getenv("DATA_DIR", "./data"))
    logs_dir = Path(os.getenv("LOGS_DIR", "./logs"))
    clients_config = os.getenv("CLIENTS_CONFIG_PATH", "./config/clients.yml")
    database_url = os.getenv("DATABASE_URL", "sqlite:///./data/bank_importer.sqlite3")

    data_dir.mkdir(parents=True, exist_ok=True)
    logs_dir.mkdir(parents=True, exist_ok=True)

    logger.info("Bank statement importer started")
    logger.info("Clients config: %s", clients_config)
    logger.info("Data directory: %s", data_dir)
    logger.info("Logs directory: %s", logs_dir)
    logger.info("Database URL: %s", database_url)

    engine = create_database_engine(database_url)
    initialize_database(engine)
    logger.info("Database initialized")

    try:
        app_config = load_clients_config(clients_config)
    except ConfigurationError as exc:
        logger.warning("Clients configuration is not ready: %s", exc)
        return BatchImportSummary(
            requested_client_slug=client_slug,
            processed_clients=0,
            imported_documents=0,
            duplicate_documents=0,
            rejected_messages=0,
            client_summaries=(),
        )

    logger.info("Loaded %d client(s)", len(app_config.clients))

    session_factory = create_session_factory(engine)
    inbox_dir = data_dir / "inbox"
    inbox_dir.mkdir(exist_ok=True)

    if client_slug is not None:
        clients = (app_config.get_client(client_slug),)
    else:
        clients = tuple(app_config.clients.values())

    client_summaries = []
    for client in clients:
        logger.info("Starting import for client: %s", client.slug)
        try:
            odoo_client = OdooClient(
                url=client.odoo.url,
                db=client.odoo.database,
                username=client.odoo.username,
                password=client.odoo.get_password(os.environ),
                version=client.odoo.version,
            )
            odoo_client.login()

            collector = ImapStatementCollector(credentials=_mail_credentials_for_client(client))

            with session_factory() as session:
                service = StatementImportService(
                    client=client,
                    collector=collector,
                    session=session,
                    inbox_dir=inbox_dir,
                    parser=GenericParser(),
                    odoo_client=odoo_client,
                )
                client_summary = service.run_once()
                session.commit()
                client_summaries.append(client_summary)

        except Exception as exc:
            audit_logger.log_technical_error(
                context=f"client_import:{client.slug}",
                error=exc,
            )
            logger.exception("Failed to process client %s: %s", client.slug, exc)

    logger.info("Bank statement importer finished")
    return BatchImportSummary(
        requested_client_slug=client_slug,
        processed_clients=len(client_summaries),
        imported_documents=sum(summary.imported_documents for summary in client_summaries),
        duplicate_documents=sum(summary.duplicate_documents for summary in client_summaries),
        rejected_messages=sum(summary.rejected_messages for summary in client_summaries),
        client_summaries=tuple(client_summaries),
    )


def main() -> None:
    load_dotenv()
    configure_logging()
    logger = logging.getLogger("bank_importer")
    run_mode = os.getenv("RUN_MODE", "once").lower()
    if run_mode == "once":
        run_import_once()
        return

    if run_mode != "poll":
        if run_mode == "api":
            from app.api.server import serve_api

            serve_api(run_import_once)
            return
        logger.warning("Unknown RUN_MODE=%s; falling back to one-shot execution", run_mode)
        run_import_once()
        return

    poll_interval = _env_int("POLL_INTERVAL_SECONDS", 300)
    if poll_interval <= 0:
        poll_interval = 300

    logger.info("Polling mode enabled: interval_seconds=%d", poll_interval)
    while True:
        run_import_once()
        time.sleep(poll_interval)


if __name__ == "__main__":
    main()
