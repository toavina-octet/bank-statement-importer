from __future__ import annotations

import json
import logging
import os
from collections.abc import Callable
from dataclasses import dataclass
from hmac import compare_digest
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

logger = logging.getLogger(__name__)

ImportRunner = Callable[[str | None], Any]


@dataclass(frozen=True)
class ApiResponse:
    status: HTTPStatus
    payload: dict[str, Any]


def serve_api(run_import_once: ImportRunner) -> None:
    host = os.getenv("API_HOST", "0.0.0.0")
    port = _env_int("API_PORT", 8080)
    token = os.getenv("API_TOKEN", "")
    if not token:
        raise RuntimeError("API_TOKEN must be configured when RUN_MODE=api")

    server = ThreadingHTTPServer((host, port), create_handler(run_import_once, token))
    logger.info("Bank importer API listening on %s:%d", host, port)
    server.serve_forever()


def create_handler(run_import_once: ImportRunner, token: str) -> type[BaseHTTPRequestHandler]:
    class ImportApiHandler(BaseHTTPRequestHandler):
        server_version = "BankImporterAPI/1.0"

        def do_GET(self) -> None:
            response = handle_api_request(
                method="GET",
                path=self.path,
                headers={},
                body=b"",
                token=token,
                run_import_once=run_import_once,
            )
            self._write_json(response.status, response.payload)

        def do_POST(self) -> None:
            response = handle_api_request(
                method="POST",
                path=self.path,
                headers={"Authorization": self.headers.get("Authorization", "")},
                body=self._read_body(),
                token=token,
                run_import_once=run_import_once,
            )
            self._write_json(response.status, response.payload)

        def log_message(self, format: str, *args: object) -> None:
            logger.info("%s - %s", self.address_string(), format % args)

        def _read_body(self) -> bytes:
            content_length = int(self.headers.get("Content-Length", "0"))
            if content_length == 0:
                return b""
            return self.rfile.read(content_length)

        def _write_json(self, status: HTTPStatus, payload: dict[str, Any]) -> None:
            body = json.dumps(payload, default=str).encode("utf-8")
            self.send_response(status.value)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    return ImportApiHandler


def handle_api_request(
    *,
    method: str,
    path: str,
    headers: dict[str, str],
    body: bytes,
    token: str,
    run_import_once: ImportRunner,
) -> ApiResponse:
    if method == "GET" and path == "/health":
        return ApiResponse(HTTPStatus.OK, {"status": "ok"})

    if method != "POST" or path != "/api/import/run":
        return ApiResponse(HTTPStatus.NOT_FOUND, {"error": "not_found"})

    if not _is_authorized(headers.get("Authorization", ""), token):
        return ApiResponse(HTTPStatus.UNAUTHORIZED, {"error": "unauthorized"})

    try:
        payload = _parse_json_body(body)
        client_slug = payload.get("client_slug")
        if client_slug is not None and not isinstance(client_slug, str):
            return ApiResponse(
                HTTPStatus.BAD_REQUEST,
                {"error": "client_slug_must_be_a_string"},
            )

        summary = run_import_once(client_slug=client_slug)
        return ApiResponse(
            HTTPStatus.OK,
            {
                "status": "success",
                "summary": summary.as_dict(),
            },
        )
    except json.JSONDecodeError:
        return ApiResponse(HTTPStatus.BAD_REQUEST, {"error": "invalid_json"})
    except Exception as exc:
        logger.exception("API import run failed: %s", exc)
        return ApiResponse(
            HTTPStatus.INTERNAL_SERVER_ERROR,
            {
                "status": "error",
                "error": exc.__class__.__name__,
                "message": str(exc),
            },
        )


def _is_authorized(header: str, expected_token: str) -> bool:
    prefix = "Bearer "
    if not header.startswith(prefix):
        return False
    return compare_digest(header[len(prefix) :], expected_token)


def _parse_json_body(body: bytes) -> dict[str, Any]:
    if not body:
        return {}
    parsed = json.loads(body.decode("utf-8"))
    if not isinstance(parsed, dict):
        raise json.JSONDecodeError("JSON body must be an object", "", 0)
    return parsed


def _env_int(name: str, default: int) -> int:
    value = os.getenv(name)
    if value is None:
        return default
    try:
        return int(value)
    except ValueError:
        return default
