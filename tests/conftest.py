"""Offline test harness: a stdlib ``http.server`` bound to ``127.0.0.1:0``.

No real network is used — every test points a :class:`roadie.Roadie` at the
ephemeral local port and drives a scripted responder. The server records each
request so tests can assert on the method, path, headers, and body the SDK sent.
"""

from __future__ import annotations

import json
import threading
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Callable, Dict, List, Optional, Sequence, Union

import pytest


@dataclass
class CapturedRequest:
    method: str
    path: str
    headers: Any  # http.client.HTTPMessage (case-insensitive .get)
    body: bytes

    def json(self) -> Any:
        return json.loads(self.body)


@dataclass
class MockResponse:
    status: int = 200
    body: Optional[Union[bytes, str]] = None
    headers: Dict[str, str] = field(default_factory=dict)
    #: When set, the response is streamed: these byte chunks are written in order.
    chunks: Optional[Sequence[bytes]] = None


Responder = Callable[[CapturedRequest], MockResponse]


def json_response(
    obj: Any, status: int = 200, headers: Optional[Dict[str, str]] = None
) -> MockResponse:
    merged = {"content-type": "application/json"}
    if headers:
        merged.update(headers)
    return MockResponse(status=status, body=json.dumps(obj), headers=merged)


def sse_response(frames: Sequence[str], headers: Optional[Dict[str, str]] = None) -> MockResponse:
    merged = {"content-type": "text/event-stream"}
    if headers:
        merged.update(headers)
    return MockResponse(status=200, headers=merged, chunks=[frame.encode("utf-8") for frame in frames])


class _Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.0"

    def log_message(self, *args: Any) -> None:  # noqa: D401 - silence test-server logging
        pass

    def _dispatch(self) -> None:
        length = int(self.headers.get("content-length") or 0)
        body = self.rfile.read(length) if length else b""
        request = CapturedRequest(
            method=self.command, path=self.path, headers=self.headers, body=body
        )
        self.server.captured.append(request)  # type: ignore[attr-defined]
        response = self.server.responder(request)  # type: ignore[attr-defined]

        self.send_response(response.status)
        for name, value in response.headers.items():
            self.send_header(name, value)

        if response.chunks is not None:
            self.end_headers()
            for chunk in response.chunks:
                self.wfile.write(chunk)
                self.wfile.flush()
            return

        data = response.body.encode("utf-8") if isinstance(response.body, str) else (response.body or b"")
        self.send_header("content-length", str(len(data)))
        self.end_headers()
        if data:
            self.wfile.write(data)

    def do_GET(self) -> None:
        self._dispatch()

    def do_POST(self) -> None:
        self._dispatch()


class MockServer:
    """Controls the running mock server: base URL, scripted responses, captured requests."""

    def __init__(self, httpd: ThreadingHTTPServer) -> None:
        self._httpd = httpd

    @property
    def base_url(self) -> str:
        host, port = self._httpd.server_address[0], self._httpd.server_address[1]
        return f"http://{host}:{port}"

    @property
    def captured(self) -> List[CapturedRequest]:
        return self._httpd.captured  # type: ignore[attr-defined]

    def respond(self, responder: Responder) -> None:
        """Install a (possibly stateful) responder callable."""
        self._httpd.responder = responder  # type: ignore[attr-defined]

    def respond_with(self, response: MockResponse) -> None:
        """Install a fixed response for every request."""
        self._httpd.responder = lambda _request: response  # type: ignore[attr-defined]


@pytest.fixture
def mock_server():
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
    httpd.captured = []  # type: ignore[attr-defined]
    httpd.responder = lambda _request: json_response({})  # type: ignore[attr-defined]
    thread = threading.Thread(target=lambda: httpd.serve_forever(poll_interval=0.02), daemon=True)
    thread.start()
    try:
        yield MockServer(httpd)
    finally:
        httpd.shutdown()
        httpd.server_close()
        thread.join(timeout=5)
