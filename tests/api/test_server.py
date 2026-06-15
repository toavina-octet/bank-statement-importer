from __future__ import annotations

import json
from dataclasses import dataclass
from http import HTTPStatus

from app.api.server import handle_api_request


@dataclass(frozen=True)
class FakeSummary:
    requested_client_slug: str | None

    def as_dict(self) -> dict[str, object]:
        return {
            "requested_client_slug": self.requested_client_slug,
            "processed_clients": 1,
            "imported_documents": 2,
            "duplicate_documents": 0,
            "rejected_messages": 0,
            "client_summaries": [],
        }


def test_health_endpoint_does_not_require_auth() -> None:
    response = handle_api_request(
        method="GET",
        path="/health",
        headers={},
        body=b"",
        token="secret-token",
        run_import_once=lambda client_slug=None: FakeSummary(client_slug),
    )

    assert response.status == HTTPStatus.OK
    assert response.payload == {"status": "ok"}


def test_import_endpoint_requires_bearer_token() -> None:
    response = handle_api_request(
        method="POST",
        path="/api/import/run",
        headers={},
        body=b"{}",
        token="secret-token",
        run_import_once=lambda client_slug=None: FakeSummary(client_slug),
    )

    assert response.status == HTTPStatus.UNAUTHORIZED
    assert response.payload == {"error": "unauthorized"}


def test_import_endpoint_runs_import_for_requested_client() -> None:
    requested_slugs: list[str | None] = []

    def fake_run(client_slug: str | None = None) -> FakeSummary:
        requested_slugs.append(client_slug)
        return FakeSummary(client_slug)

    response = handle_api_request(
        method="POST",
        path="/api/import/run",
        headers={"Authorization": "Bearer secret-token"},
        body=json.dumps({"client_slug": "sit_palais"}).encode("utf-8"),
        token="secret-token",
        run_import_once=fake_run,
    )

    assert response.status == HTTPStatus.OK
    assert requested_slugs == ["sit_palais"]
    assert response.payload["status"] == "success"
    assert response.payload["summary"]["requested_client_slug"] == "sit_palais"
    assert response.payload["summary"]["imported_documents"] == 2


def test_import_endpoint_rejects_invalid_client_slug() -> None:
    response = handle_api_request(
        method="POST",
        path="/api/import/run",
        headers={"Authorization": "Bearer secret-token"},
        body=json.dumps({"client_slug": 123}).encode("utf-8"),
        token="secret-token",
        run_import_once=lambda client_slug=None: FakeSummary(client_slug),
    )

    assert response.status == HTTPStatus.BAD_REQUEST
    assert response.payload == {"error": "client_slug_must_be_a_string"}
