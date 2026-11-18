"""`drillcore review`: the review page, served from this computer to this computer only.

The page puts a note and the stored source it cites side by side and steps through every claim `check` judges (see
`review`). It's served by the standard library's HTTP server on 127.0.0.1, at the port set aside for this tool
(`identity.PORT`), or any free one when that's taken. Nothing outside the page is loaded: no script, font or style
from anywhere else.

What reaches the server is held to the page it served:

- A request must name this computer as its host, as 127.0.0.1 or localhost and this port, so a page elsewhere can't
  reach it by a name it controls (DNS rebinding).
- Every request for data carries a token the page was given when it loaded, in a header of its own. A page from
  another site can't send that header here without the server's leave, which it never gives, so it can neither read
  the notes nor change them.
- The page may run only its own script and style (its Content-Security-Policy), and shows every note and source as
  text, never as markup.

What the page writes, it writes through `review`: a line of a note, in place of the line it showed (`edit_line`), a
mark in checks/review.csv, or a waiver in checks/waivers.csv. The example workspace is shown but never changed.
"""
import argparse
import contextlib
import json
import secrets
import sys
import webbrowser
from collections.abc import Callable
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlsplit

from . import identity, review, sourcedb
from .workspace import Workspace, WorkspaceError

STATIC = Path(__file__).with_name("static")
# What the server hands out as files, by path: the page and what it loads, nothing else.
FILES = {"/": ("review.html", "text/html; charset=utf-8"),
         "/review.css": ("review.css", "text/css; charset=utf-8"),
         "/review.js": ("review.js", "text/javascript; charset=utf-8")}
# The header a request carries the page's token in: its name, not a secret.
TOKEN_HEADER = "x-review-token"  # noqa: S105
# The largest request the server reads: a line of a note, a mark or a waiver is far smaller.
MOST_BYTES = 1_000_000
POLICY = ("default-src 'none'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; "
          "base-uri 'none'; form-action 'none'; frame-ancestors 'none'")
SAFE = {"X-Content-Type-Options": "nosniff", "Referrer-Policy": "no-referrer", "X-Frame-Options": "DENY",
        "Cache-Control": "no-store", "Cross-Origin-Resource-Policy": "same-origin"}

Response = tuple[int, dict[str, str], bytes]


class Refused(Exception):
    """A request the server won't serve, with the status and why."""

    def __init__(self, status: HTTPStatus, message: str) -> None:
        super().__init__(message)
        self.status = status


class App:
    """The review of one workspace, and what the page asks of it. Each request opens the database and closes it, so
    the server holds nothing open between requests and other commands can run beside it."""

    def __init__(self, ws: Workspace, port: int, token: str = "") -> None:
        self.ws = ws
        self.port = port
        self.token = token or secrets.token_urlsafe(32)
        self.review: review.Review | None = None
        # What the last review read of the sources, used again after an edit to a note, which changes no source.
        self.kept = review.Kept()
        # Each line the page changed, as (note, line, what it was, what it became), the last last.
        self.undo: list[tuple[str, int, str, str]] = []

    # ---- the review

    def current(self) -> review.Review:
        if self.review is None:
            self.refresh()
        assert self.review is not None
        return self.review

    def refresh(self, reread: bool = False) -> None:
        """Run the checks again. `reread` reads every source again too, for a page asked to recheck: another command,
        such as `fetch`, may have changed them since."""
        if reread:
            self.kept = review.Kept()
        with contextlib.closing(sourcedb.connect(self.ws)) as con:
            self.review = review.gather(self.ws, con, self.kept)

    def state(self) -> dict[str, Any]:
        found = self.current().to_json()
        found["workspace"] = {"name": str(self.ws.config().get("name") or self.ws.root.name), "root": str(self.ws.root),
                              "example": self.ws.is_example}
        found["readOnly"] = self.ws.is_example
        found["canUndo"] = bool(self.undo)
        found["slug"] = identity.SLUG
        found["name"] = identity.NAME
        return found

    def claim(self, asked: Any) -> review.Claim:
        if not isinstance(asked, dict):
            raise Refused(HTTPStatus.BAD_REQUEST, "Name the claim by its note, line, check and item.")
        found = self.current().find(str(asked.get("note", "")), int(asked.get("line", 0) or 0), str(asked.get("check", "")),
                                    str(asked.get("item", "")))
        if found is None:
            raise Refused(HTTPStatus.CONFLICT, "That claim isn't in the review any more. Recheck, then try again.")
        return found

    # ---- requests

    def respond(self, method: str, target: str, headers: dict[str, str], body: bytes) -> Response:
        """What to send back for one request: the status, the headers and the body."""
        headers = {name.lower(): value for name, value in headers.items()}
        try:
            if headers.get("host", "") not in (f"127.0.0.1:{self.port}", f"localhost:{self.port}"):
                raise Refused(HTTPStatus.MISDIRECTED_REQUEST, "This server answers only to 127.0.0.1 and localhost.")
            path, query = urlsplit(target).path, parse_qs(urlsplit(target).query)
            if method == "GET" and path in FILES:
                return self.file(path)
            if not path.startswith("/api/"):
                raise Refused(HTTPStatus.NOT_FOUND, "Nothing here.")
            if not secrets.compare_digest(headers.get(TOKEN_HEADER, ""), self.token):
                raise Refused(HTTPStatus.FORBIDDEN, "The page's token is missing or out of date. Load the page again.")
            if method == "GET":
                return self.json(self.read(path, query))
            if method == "POST":
                if headers.get("content-type", "").split(";")[0].strip() != "application/json":
                    raise Refused(HTTPStatus.UNSUPPORTED_MEDIA_TYPE, "Send JSON.")
                try:
                    asked = json.loads(body.decode("utf-8") or "{}")
                except (UnicodeDecodeError, json.JSONDecodeError):
                    raise Refused(HTTPStatus.BAD_REQUEST, "That isn't JSON.") from None
                return self.json(self.write(path, asked if isinstance(asked, dict) else {}))
            raise Refused(HTTPStatus.METHOD_NOT_ALLOWED, "Only GET and POST.")
        except Refused as refused:
            return self.json({"error": str(refused)}, refused.status)
        except (review.ReviewError, WorkspaceError) as problem:
            return self.json({"error": str(problem)}, HTTPStatus.CONFLICT)
        except (ValueError, TypeError):
            return self.json({"error": "That request names something in a way the review can't read."}, HTTPStatus.BAD_REQUEST)

    def file(self, path: str) -> Response:
        name, kind = FILES[path]
        content = (STATIC / name).read_bytes()
        extra = {}
        if name.endswith(".html"):
            content = content.replace(b"__REVIEW_TOKEN__", self.token.encode("ascii"))
            extra["Content-Security-Policy"] = POLICY
        return HTTPStatus.OK, {"Content-Type": kind, **SAFE, **extra}, content

    def json(self, payload: dict[str, Any], status: int = HTTPStatus.OK) -> Response:
        return status, {"Content-Type": "application/json; charset=utf-8", **SAFE}, json.dumps(payload).encode("utf-8")

    def read(self, path: str, query: dict[str, list[str]]) -> dict[str, Any]:
        if path == "/api/state":
            return self.state()
        if path == "/api/source":
            asked = (query.get("id") or [""])[0]
            sources = self.current().sources
            if not asked.isdigit() or int(asked) >= len(sources):
                raise Refused(HTTPStatus.NOT_FOUND, "No such source.")
            with contextlib.closing(sourcedb.connect(self.ws)) as con:
                return review.source_text(con, sources[int(asked)].url)
        raise Refused(HTTPStatus.NOT_FOUND, "Nothing here.")

    def write(self, path: str, asked: dict[str, Any]) -> dict[str, Any]:
        actions: dict[str, Callable[[dict[str, Any]], None]] = {
            "/api/recheck": lambda _: self.refresh(reread=True),
            "/api/mark": self.mark,
            "/api/accept": self.accept,
            "/api/edit": self.edit,
            "/api/undo": self.undo_last,
        }
        if path not in actions:
            raise Refused(HTTPStatus.NOT_FOUND, "Nothing here.")
        actions[path](asked)
        return self.state()

    def mark(self, asked: dict[str, Any]) -> None:
        review.writable(self.ws)
        claim = self.claim(asked.get("claim"))
        marks = review.set_mark(self.ws, claim, str(asked.get("mark", "")), str(asked.get("comment", "")), str(asked.get("by", "")))
        review.apply_marks(self.current(), marks)

    def accept(self, asked: dict[str, Any]) -> None:
        review.accept(self.ws, self.claim(asked.get("claim")), str(asked.get("reason", "")), str(asked.get("by", "")))
        self.refresh()

    def edit(self, asked: dict[str, Any]) -> None:
        note, line, old, new = str(asked.get("note", "")), int(asked.get("line", 0) or 0), str(asked.get("old", "")), str(asked.get("new", ""))
        if old == new:
            return
        review.edit_line(self.ws, note, line, old, new)
        self.undo.append((note, line, old, new))
        self.refresh()

    def undo_last(self, asked: dict[str, Any]) -> None:
        if not self.undo:
            raise review.ReviewError("Nothing to undo.")
        note, line, old, new = self.undo[-1]
        review.edit_line(self.ws, note, line, new, old)
        self.undo.pop()
        self.refresh()


class Handler(BaseHTTPRequestHandler):
    """Hands each request to the App and sends back what it says."""
    server_version = f"{identity.SLUG}-review"
    sys_version = ""

    def do_GET(self) -> None:
        self.answer("GET")

    def do_POST(self) -> None:
        self.answer("POST")

    def answer(self, method: str) -> None:
        app: App = self.server.app  # type: ignore[attr-defined]
        length = int(self.headers.get("Content-Length") or 0)
        if length > MOST_BYTES:
            status, headers, body = app.json({"error": "That request is too large."}, HTTPStatus.REQUEST_ENTITY_TOO_LARGE)
        else:
            status, headers, body = app.respond(method, self.path, dict(self.headers.items()), self.rfile.read(length) if length else b"")
        self.send_response(status)
        for name, value in headers.items():
            self.send_header(name, value)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args: Any) -> None:
        """Quiet: a request line names a note, and the terminal isn't the place for every one."""


def serve(app: App, port: int) -> HTTPServer:
    """A server for the app on 127.0.0.1, at the port given, or any free port when that one's taken."""
    try:
        server = HTTPServer(("127.0.0.1", port), Handler)
    except OSError:
        server = HTTPServer(("127.0.0.1", 0), Handler)
    app.port = server.server_address[1]
    server.app = app  # type: ignore[attr-defined]
    return server


def run(ws: Workspace, args: argparse.Namespace) -> int:
    """Serve the review page until stopped, and open it in a browser unless asked not to."""
    app = App(ws, args.port)
    print(f"Reading the notes and their sources in {ws.root} ...", flush=True)
    app.refresh()
    server = serve(app, args.port)
    address = f"http://127.0.0.1:{app.port}/"
    claims = app.current().claims
    print(f"{len(claims)} claim{'' if len(claims) == 1 else 's'} to review at {address}")
    if app.port != args.port:
        print(f"Port {args.port} was taken, so it's on {app.port}.", file=sys.stderr)
    if ws.is_example:
        print("This is the example workspace, so the page shows it and changes nothing.", file=sys.stderr)
    print("Press Ctrl+C to stop.", flush=True)
    if not args.no_open:
        webbrowser.open(address)
    with server:
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            print("stopped")
    return 0
