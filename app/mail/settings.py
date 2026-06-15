from __future__ import annotations

from collections.abc import Mapping

from app.config import ConfigurationError
from app.mail.models import MailCredentials


def load_mail_credentials(environ: Mapping[str, str]) -> MailCredentials:
    return MailCredentials(
        host=_required_string(environ, "IMAP_HOST"),
        port=_required_int(environ, "IMAP_PORT", default=993),
        username=_required_string(environ, "IMAP_USER"),
        password=_required_string(environ, "IMAP_PASSWORD"),
        folder=environ.get("IMAP_FOLDER", "INBOX").strip() or "INBOX",
        use_ssl=_optional_bool(environ, "IMAP_USE_SSL", default=True),
    )


def _required_string(environ: Mapping[str, str], key: str) -> str:
    value = environ.get(key)
    if not value or not value.strip():
        raise ConfigurationError(f"Missing required environment variable: {key}")
    return value.strip()


def _required_int(environ: Mapping[str, str], key: str, default: int) -> int:
    raw_value = environ.get(key, str(default))
    try:
        value = int(raw_value)
    except ValueError as exc:
        raise ConfigurationError(f"Environment variable {key} must be an integer") from exc

    if value <= 0:
        raise ConfigurationError(f"Environment variable {key} must be positive")
    return value


def _optional_bool(environ: Mapping[str, str], key: str, default: bool) -> bool:
    raw_value = environ.get(key)
    if raw_value is None:
        return default

    normalized = raw_value.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False

    raise ConfigurationError(f"Environment variable {key} must be a boolean")
