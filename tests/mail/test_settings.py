import pytest

from app.config import ConfigurationError
from app.mail import load_mail_credentials


def test_load_mail_credentials_from_environment() -> None:
    credentials = load_mail_credentials(
        {
            "IMAP_HOST": "imap.example.com",
            "IMAP_PORT": "993",
            "IMAP_USER": "user@example.com",
            "IMAP_PASSWORD": "secret",
            "IMAP_FOLDER": "Statements",
            "IMAP_USE_SSL": "true",
        }
    )

    assert credentials.host == "imap.example.com"
    assert credentials.port == 993
    assert credentials.username == "user@example.com"
    assert credentials.password == "secret"
    assert credentials.folder == "Statements"
    assert credentials.use_ssl is True


def test_load_mail_credentials_rejects_invalid_port() -> None:
    with pytest.raises(ConfigurationError, match="IMAP_PORT"):
        load_mail_credentials(
            {
                "IMAP_HOST": "imap.example.com",
                "IMAP_PORT": "invalid",
                "IMAP_USER": "user@example.com",
                "IMAP_PASSWORD": "secret",
            }
        )
