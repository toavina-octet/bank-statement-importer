from pathlib import Path

import pytest

from app.config import ConfigurationError, load_clients_config


def test_loads_example_clients_config() -> None:
    config = load_clients_config(Path("config/clients.example.yml"))

    assert set(config.clients) == {"vinamora", "bcp", "octet", "sem", "sit_palais"}
    assert config.get_client("vinamora").odoo.version == 19
    assert config.get_client("sit_palais").odoo.version == 14
    assert config.get_client("vinamora").mailbox.host == "imap.example.com"
    assert config.get_client("vinamora").mailbox.port == 993
    assert config.get_client("octet").mailbox.folder == "INBOX"


def test_authorized_sender_check_is_case_insensitive() -> None:
    config = load_clients_config(Path("config/clients.example.yml"))
    banking = config.get_client("vinamora").banking

    assert banking.is_authorized_sender("RELEVES@example-bank.com")


def test_missing_required_client_field_raises(tmp_path: Path) -> None:
    config_path = tmp_path / "clients.yml"
    config_path.write_text(
        """
clients:
  vinamora:
    odoo:
      version: 19
      url: "https://odoo.example.com"
      database: "vinamora"
      username: "technical-user@example.com"
      password_env: "VINAMORA_ODOO_PASSWORD"
    mailbox:
      email: "bank-statements@example.com"
      host: "imap.example.com"
      port: 993
      username: "bank-statements@example.com"
      password_env: "VINAMORA_IMAP_PASSWORD"
    banking:
      authorized_senders: []
""",
        encoding="utf-8",
    )

    with pytest.raises(ConfigurationError, match="authorized_senders"):
        load_clients_config(config_path)


def test_odoo_password_is_resolved_from_environment() -> None:
    config = load_clients_config(Path("config/clients.example.yml"))
    password = config.get_client("vinamora").odoo.get_password(
        {"VINAMORA_ODOO_PASSWORD": "secret"}
    )

    assert password == "secret"


def test_mailbox_password_is_resolved_from_environment() -> None:
    config = load_clients_config(Path("config/clients.example.yml"))
    password = config.get_client("vinamora").mailbox.get_password(
        {"VINAMORA_IMAP_PASSWORD": "secret"}
    )

    assert password == "secret"
