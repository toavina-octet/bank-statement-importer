from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from email.utils import parseaddr

from app.config.exceptions import ConfigurationError


@dataclass(frozen=True)
class OdooSettings:
    version: int
    url: str
    database: str
    username: str
    password_env: str

    def get_password(self, environ: Mapping[str, str]) -> str:
        password = environ.get(self.password_env)
        if not password:
            raise ConfigurationError(
                f"Missing Odoo password environment variable: {self.password_env}"
            )
        return password


@dataclass(frozen=True)
class MailboxSettings:
    email: str
    host: str
    port: int
    username: str
    password_env: str
    folder: str = "INBOX"
    use_ssl: bool = True

    def get_password(self, environ: Mapping[str, str]) -> str:
        password = environ.get(self.password_env)
        if not password:
            raise ConfigurationError(
                f"Missing mailbox password environment variable: {self.password_env}"
            )
        return password


@dataclass(frozen=True)
class BankingSettings:
    authorized_senders: tuple[str, ...]

    def is_authorized_sender(self, sender: str) -> bool:
        normalized_sender = _normalize_email_address(sender)
        return normalized_sender in {
            _normalize_email_address(item) for item in self.authorized_senders
        }


@dataclass(frozen=True)
class ClientConfig:
    slug: str
    odoo: OdooSettings
    mailbox: MailboxSettings
    banking: BankingSettings


@dataclass(frozen=True)
class AppConfig:
    clients: Mapping[str, ClientConfig]

    def get_client(self, slug: str) -> ClientConfig:
        try:
            return self.clients[slug]
        except KeyError as exc:
            raise ConfigurationError(f"Unknown client: {slug}") from exc


def _normalize_email_address(value: str) -> str:
    parsed_name, parsed_address = parseaddr(value)
    return (parsed_address or parsed_name or value).strip().lower()
