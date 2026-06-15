import logging
from logging.handlers import RotatingFileHandler

from app.main import configure_logging


def test_configure_logging_creates_rotating_file_handler(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("LOGS_DIR", str(tmp_path))
    monkeypatch.setenv("LOG_FILE", "test-importer.log")
    monkeypatch.setenv("LOG_MAX_BYTES", "1024")
    monkeypatch.setenv("LOG_BACKUP_COUNT", "2")

    configure_logging()

    root_logger = logging.getLogger()
    file_handlers = [
        handler for handler in root_logger.handlers if isinstance(handler, RotatingFileHandler)
    ]

    assert len(file_handlers) == 1
    assert file_handlers[0].baseFilename == str(tmp_path / "test-importer.log")
    assert file_handlers[0].maxBytes == 1024
    assert file_handlers[0].backupCount == 2

    logging.getLogger("bank_importer.test").info("persisted log line")
    file_handlers[0].flush()

    assert "persisted log line" in (tmp_path / "test-importer.log").read_text()
