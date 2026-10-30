"""A stand-in GitLab for the client's tests: a local HTTP server answering the REST calls a test gives it, the way
GitLab's API documentation shows them (JSON bodies, `X-Next-Page` paging, error codes), and recording every request
it gets, with the token header it carried.

    with FakeGitLab({"/api/v4/user": {"username": "ba.user"}}) as gitlab:
        gitlab.url           # http://127.0.0.1:<port>
        gitlab.requests      # [(path, query, token)]

A route's value is the JSON body; a list of `Page`s pages it; an `Error` answers with its code. A write's route is
keyed by its method and path (`"POST /api/v4/projects/101/issues"`), its value the body to answer with or a function
of the body sent; `gitlab.writes` records each one, as (method, path, body, token).
"""

from __future__ import annotations

import json
import threading
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse


@dataclass
class Page:
    body: object


@dataclass
class Error:
    code: int


class FakeGitLab:
    def __init__(self, routes: dict):
        self.routes = routes
        self.requests: list[tuple[str, dict, str | None]] = []
        self.writes: list[tuple[str, str, dict, str | None]] = []
        fake = self

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):  # noqa: N802 (the stdlib's name)
                url = urlparse(self.path)
                query = {k: v[0] for k, v in parse_qs(url.query).items()}
                fake.requests.append((url.path, query, self.headers.get("PRIVATE-TOKEN")))
                route = fake.routes.get(url.path)
                if route is None:
                    return self._send(404, {"message": "404 Not Found"})
                if isinstance(route, Error):
                    return self._send(route.code, {"message": f"{route.code}"})
                if isinstance(route, list) and route and isinstance(route[0], Page):
                    number = int(query.get("page", "1"))
                    following = str(number + 1) if number < len(route) else ""
                    return self._send(200, route[number - 1].body, {"X-Next-Page": following})
                return self._send(200, route, {"X-Next-Page": ""})

            def do_POST(self):  # noqa: N802
                self._write("POST")

            def do_PUT(self):  # noqa: N802
                self._write("PUT")

            def _write(self, method: str):
                path = urlparse(self.path).path
                length = int(self.headers.get("Content-Length") or 0)
                body = json.loads(self.rfile.read(length) or b"{}")
                fake.writes.append((method, path, body, self.headers.get("PRIVATE-TOKEN")))
                route = fake.routes.get(f"{method} {path}")
                if route is None:
                    return self._send(404, {"message": "404 Not Found"})
                if isinstance(route, Error):
                    return self._send(route.code, {"message": f"{route.code}"})
                return self._send(201 if method == "POST" else 200, route(body) if callable(route) else route)

            def _send(self, code: int, body, headers: dict | None = None):
                data = json.dumps(body).encode("utf-8")
                self.send_response(code)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(data)))
                for name, value in (headers or {}).items():
                    self.send_header(name, value)
                self.end_headers()
                self.wfile.write(data)

            def log_message(self, *args):  # quiet
                pass

        self._server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.url = f"http://127.0.0.1:{self._server.server_address[1]}"

    def __enter__(self) -> "FakeGitLab":
        threading.Thread(target=self._server.serve_forever, daemon=True).start()
        return self

    def __exit__(self, *exc) -> None:
        self._server.shutdown()
        self._server.server_close()
