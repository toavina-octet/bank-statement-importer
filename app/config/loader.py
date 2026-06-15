from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from app.config.exceptions import ConfigurationError
from app.config.models import (
    AppConfig,
    BankingSettings,
    ClientConfig,
    MailboxSettings,
    OdooSettings,
)


def load_clients_config(path: str | Path) -> AppConfig:
    config_path = Path(path)
    if not config_path.exists():
        raise ConfigurationError(f"Clients configuration file not found: {config_path}")

    with config_path.open(encoding="utf-8") as file:
        raw_config = yaml.safe_load(file)

    if raw_config is None:
        raise ConfigurationError(f"Clients configuration file is empty: {config_path}")
    if not isinstance(raw_config, dict):
        raise ConfigurationError("Clients configuration root must be a mapping")

    clients_data = _required_mapping(raw_config, "clients")
    if not clients_data:
        raise ConfigurationError("At least one client must be configured")

    clients: dict[str, ClientConfig] = {}
    for slug, client_data in clients_data.items():
        if not isinstance(slug, str) or not slug.strip():
            raise ConfigurationError("Client keys must be non-empty strings")
        clients[slug] = _parse_client(slug=slug, data=client_data)

    return AppConfig(clients=clients)


def _parse_client(slug: str, data: Any) -> ClientConfig:
    if not isinstance(data, dict):
        raise ConfigurationError(f"Client '{slug}' must be a mapping")

    odoo = _required_mapping(data, "odoo", prefix=f"clients.{slug}")
    mailbox = _required_mapping(data, "mailbox", prefix=f"clients.{slug}")
    banking = _required_mapping(data, "banking", prefix=f"clients.{slug}")

    return ClientConfig(
        slug=slug,
        odoo=OdooSettings(
            version=_required_positive_int(odoo, "version", prefix=f"clients.{slug}.odoo"),
            url=_required_string(odoo, "url", prefix=f"clients.{slug}.odoo"),
            database=_required_string(odoo, "database", prefix=f"clients.{slug}.odoo"),
            username=_required_string(odoo, "username", prefix=f"clients.{slug}.odoo"),
            password_env=_required_string(odoo, "password_env", prefix=f"clients.{slug}.odoo"),
        ),
        mailbox=MailboxSettings(
            email=_required_string(mailbox, "email", prefix=f"clients.{slug}.mailbox"),
            host=_required_string(mailbox, "host", prefix=f"clients.{slug}.mailbox"),
            port=_required_positive_int(mailbox, "port", prefix=f"clients.{slug}.mailbox"),
            username=_required_string(mailbox, "username", prefix=f"clients.{slug}.mailbox"),
            password_env=_required_string(
                mailbox,
                "password_env",
                prefix=f"clients.{slug}.mailbox",
            ),
            folder=_optional_string(mailbox, "folder", default="INBOX"),
            use_ssl=_optional_bool(mailbox, "use_ssl", default=True),
        ),
        banking=BankingSettings(
            authorized_senders=_required_string_tuple(
                banking,
                "authorized_senders",
                prefix=f"clients.{slug}.banking",
            ),
        ),
    )


def _required_mapping(data: dict[str, Any], key: str, prefix: str = "") -> dict[str, Any]:
    value = data.get(key)
    location = f"{prefix}.{key}" if prefix else key
    if not isinstance(value, dict):
        raise ConfigurationError(f"Configuration key '{location}' must be a mapping")
    return value


def _required_string(data: dict[str, Any], key: str, prefix: str) -> str:
    value = data.get(key)
    location = f"{prefix}.{key}"
    if not isinstance(value, str) or not value.strip():
        raise ConfigurationError(f"Configuration key '{location}' must be a non-empty string")
    return value.strip()


def _optional_string(data: dict[str, Any], key: str, default: str) -> str:
    value = data.get(key, default)
    if not isinstance(value, str) or not value.strip():
        raise ConfigurationError(f"Configuration key '{key}' must be a non-empty string")
    return value.strip()


def _optional_bool(data: dict[str, Any], key: str, default: bool) -> bool:
    value = data.get(key, default)
    if not isinstance(value, bool):
        raise ConfigurationError(f"Configuration key '{key}' must be a boolean")
    return value


def _required_positive_int(data: dict[str, Any], key: str, prefix: str) -> int:
    value = data.get(key)
    location = f"{prefix}.{key}"
    if not isinstance(value, int) or value <= 0:
        raise ConfigurationError(f"Configuration key '{location}' must be a positive integer")
    return value


def _required_string_tuple(data: dict[str, Any], key: str, prefix: str) -> tuple[str, ...]:
    value = data.get(key)
    location = f"{prefix}.{key}"
    if not isinstance(value, list) or not value:
        raise ConfigurationError(f"Configuration key '{location}' must be a non-empty list")

    normalized_values: list[str] = []
    for index, item in enumerate(value):
        if not isinstance(item, str) or not item.strip():
            raise ConfigurationError(
                f"Configuration key '{location}[{index}]' must be a non-empty string"
            )
        normalized_values.append(item.strip())

    return tuple(normalized_values)
