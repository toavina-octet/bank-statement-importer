from datetime import UTC, datetime

from sqlalchemy import create_engine

from app.database import create_session_factory, initialize_database
from app.duplicate import DuplicateDetector, calculate_sha256


def test_calculate_sha256() -> None:
    assert calculate_sha256(b"statement") == (
        "b111c6e1d318f203063e5c16bab43c108326af0aa2f7b65760c95547a43dbe52"
    )


def test_register_document_detects_duplicate() -> None:
    engine = create_engine("sqlite:///:memory:", future=True)
    initialize_database(engine)
    session_factory = create_session_factory(engine)

    with session_factory() as session:
        detector = DuplicateDetector(session)

        first_registration = detector.register_document(
            content=b"%PDF-1.4",
            filename="statement.pdf",
            message_uid="101",
            received_at=datetime(2026, 6, 9, 10, 0, tzinfo=UTC),
        )
        second_registration = detector.register_document(
            content=b"%PDF-1.4",
            filename="statement-copy.pdf",
            message_uid="102",
            received_at=datetime(2026, 6, 9, 11, 0, tzinfo=UTC),
        )

        assert first_registration is not None
        assert second_registration is None
        assert detector.is_duplicate(b"%PDF-1.4") is True
        assert detector.is_duplicate(b"other") is False
