"""Loopback-only desktop service and launcher for MIC-50-90 1.0.0."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import mimetypes
import multiprocessing
import os
from pathlib import Path, PurePosixPath
import re
import secrets
import threading
from urllib.parse import parse_qs, quote, unquote, urlsplit
import webbrowser
from zipfile import ZIP_DEFLATED, ZipFile

from ._version import __version__
from .gui_forms import decode_payload, desktop_examples, validate_payload
from .gui_worker import execute_job, write_json

MAX_BODY_BYTES = 16 * 1024 * 1024


def _default_output_root():
    base = Path(os.environ.get("LOCALAPPDATA", Path.home() / ".local" / "share"))
    return base / "MIC-50-90" / "analyses"


class DesktopServer(ThreadingHTTPServer):
    """One local session with isolated, cancellable child-process analyses."""

    daemon_threads = True

    def __init__(self, port, output_root, assets):
        self.token = secrets.token_urlsafe(32)
        self.output_root = Path(output_root).resolve()
        self.assets = Path(assets).resolve()
        self.jobs = {}
        self.jobs_lock = threading.RLock()
        super().__init__(("127.0.0.1", port), DesktopHandler)

    @property
    def origin(self):
        return f"http://127.0.0.1:{self.server_port}"

    @property
    def url(self):
        return self.origin + "/#token=" + self.token

    def create_job(self, payload):
        with self.jobs_lock:
            if any(self.job_status(key)["status"] == "running" for key in self.jobs):
                raise RuntimeError("Another analysis is running. Wait for it or cancel it before starting another.")
            job_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ-") + secrets.token_hex(5)
            directory = self.output_root / job_id
            directory.mkdir(parents=True, exist_ok=False)
            process = multiprocessing.get_context("spawn").Process(target=execute_job, args=(payload, directory), daemon=True)
            self.jobs[job_id] = {"directory": directory, "process": process, "cancelled": False}
            try:
                process.start()
            except Exception:
                self.jobs[job_id]["cancelled"] = True
                raise
            return self.job_status(job_id)

    def job_status(self, job_id):
        with self.jobs_lock:
            job = self.jobs[job_id]
            process = job["process"]
            status_file = job["directory"] / "job-status.json"
            if job["cancelled"]:
                status = {"status": "cancelled", "message": "Analysis cancelled. Incomplete outputs are not presented as completed results."}
            elif process.is_alive():
                status = {"status": "running", "message": "Calculating with the MIC-50-90 analysis engine."}
            elif status_file.is_file():
                status = json.loads(status_file.read_text(encoding="utf-8"))
                process.join(timeout=0)
            else:
                status = {"status": "failed", "message": "The calculation process stopped without a complete result."}
            status.update(job_id=job_id, output_directory=str(job["directory"] / "output"), files=[])
            if status["status"] in {"completed", "refused"}:
                status["files"] = [{"name": name, "url": f"/api/jobs/{job_id}/files/{quote(name)}?token={self.token}"}
                                   for name in self.allowed_files(job_id)]
                status["archive_url"] = f"/api/jobs/{job_id}/archive?token={self.token}"
            return status

    def allowed_files(self, job_id):
        output = self.jobs[job_id]["directory"] / "output"
        allowed = {}
        for file in sorted(output.rglob("*")):
            if file.is_file() and not file.is_symlink() and file.suffix in {".html", ".json", ".csv"}:
                resolved = file.resolve()
                if resolved.is_relative_to(output.resolve()):
                    allowed[file.relative_to(output).as_posix()] = file
        return allowed

    def cancel_job(self, job_id):
        with self.jobs_lock:
            job = self.jobs[job_id]
            if self.job_status(job_id)["status"] == "running":
                job["cancelled"] = True
                job["process"].terminate()
                job["process"].join(timeout=5)
                if job["process"].is_alive():
                    job["process"].kill()
                    job["process"].join(timeout=5)
            return self.job_status(job_id)

    def server_close(self):
        for job_id in list(self.jobs):
            self.cancel_job(job_id)
        super().server_close()


class DesktopHandler(BaseHTTPRequestHandler):
    """Strict routes: no directory listing, arbitrary input paths or CORS."""

    server_version = "MIC-50-90/1.0.0"

    def log_message(self, *_args):
        # Download URLs carry a session token; never copy it to access logs.
        pass

    def _send(self, code, body, *, content_type="application/json; charset=utf-8", extra=None):
        if isinstance(body, (dict, list)):
            body = json.dumps(body, ensure_ascii=False, allow_nan=False).encode("utf-8")
        elif isinstance(body, str):
            body = body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("X-Frame-Options", "SAMEORIGIN")
        self.send_header("Content-Security-Policy", (extra or {}).get("Content-Security-Policy",
            "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'self'"))
        for key, value in (extra or {}).items():
            if key != "Content-Security-Policy":
                self.send_header(key, value)
        self.end_headers()
        self.wfile.write(body)

    def _guard(self, api=False, download=False):
        expected = f"127.0.0.1:{self.server.server_port}"
        if self.headers.get_all("Host", []) != [expected]:
            self._discard_rejected_body()
            self._send(403, {"error": "This service accepts only its local address."})
            return False
        origin = self.headers.get("Origin")
        if origin and origin != self.server.origin:
            self._discard_rejected_body()
            self._send(403, {"error": "Requests from another origin are not accepted."})
            return False
        if api:
            token = self.headers.get("Authorization", "").removeprefix("Bearer ")
            if download and not token:
                token = parse_qs(urlsplit(self.path).query).get("token", [""])[0]
                if not token:
                    cookie = SimpleCookie()
                    try:
                        cookie.load(self.headers.get("Cookie", ""))
                        token = cookie["mic50_download"].value if "mic50_download" in cookie else ""
                    except Exception:
                        token = ""
            if not secrets.compare_digest(token, self.server.token):
                self._discard_rejected_body()
                self._send(403, {"error": "The local session token is missing or invalid. Reopen the application."})
                return False
        return True

    def _discard_rejected_body(self):
        # Consume a bounded body before closing: Windows otherwise resets the
        # socket and can hide the useful rejection message from the browser.
        if self.command != "POST":
            return
        try:
            size = int(self.headers.get("Content-Length", "0"))
            if 0 < size <= MAX_BODY_BYTES:
                self.connection.settimeout(.5)
                self.rfile.read(size)
        except (ValueError, OSError):
            pass

    def _body(self):
        if self.headers.get("Transfer-Encoding"):
            raise ValueError("Chunked requests are not supported.")
        if self.headers.get("Content-Type", "").split(";")[0].strip() != "application/json":
            raise ValueError("Send the request as application/json.")
        sizes = self.headers.get_all("Content-Length", [])
        if len(sizes) != 1:
            raise ValueError("Supply one Content-Length header.")
        size = int(sizes[0])
        if not 0 <= size <= MAX_BODY_BYTES:
            raise ValueError("The submitted input exceeds the 16 MB local upload limit.")
        self.connection.settimeout(20)
        text = self.rfile.read(size).decode("utf-8")
        return decode_payload(text)

    def do_GET(self):
        path = unquote(urlsplit(self.path).path)
        download = bool(re.fullmatch(r"/api/jobs/[^/]+/(?:files/.+|archive)", path))
        if not self._guard(api=path.startswith("/api/"), download=download):
            return
        if path == "/api/session":
            self._send(200, {"software": "MIC-50-90", "version": __version__, "examples": desktop_examples(),
                "units": ["mg/L", "ug/mL"], "output_root": str(self.server.output_root)})
            return
        match = re.fullmatch(r"/api/jobs/([A-Za-z0-9-]+)(?:/(files/(.+)|archive))?", path)
        if match and match[1] in self.server.jobs:
            job_id, action, name = match.groups()
            status = self.server.job_status(job_id)
            if action is None:
                self._send(200, status)
                return
            if status["status"] not in {"completed", "refused"}:
                self._send(409, {"error": "Files are available only after a complete analysis or a documented refusal."})
                return
            allowed = self.server.allowed_files(job_id)
            if action == "archive":
                from io import BytesIO
                buffer = BytesIO()
                with ZipFile(buffer, "w", compression=ZIP_DEFLATED) as archive:
                    for filename, file in allowed.items():
                        archive.write(file, filename)
                self._send(200, buffer.getvalue(), content_type="application/zip", extra={
                    "Content-Disposition": f'attachment; filename="MIC-50-90-{job_id}.zip"'})
                return
            if name in allowed and ".." not in PurePosixPath(name).parts:
                file = allowed[name]
                content_type = mimetypes.guess_type(file.name)[0] or "application/octet-stream"
                extra = {"Set-Cookie": f"mic50_download={self.server.token}; HttpOnly; SameSite=Strict; Path=/api/jobs/{job_id}/files/"}
                if file.suffix == ".html":
                    extra["Content-Security-Policy"] = "sandbox allow-same-origin; default-src 'none'; style-src 'unsafe-inline'; font-src data:; img-src data:; base-uri 'none'; frame-ancestors 'self'"
                else:
                    extra["Content-Disposition"] = f'attachment; filename="{file.name}"'
                self._send(200, file.read_bytes(), content_type=content_type + ("; charset=utf-8" if file.suffix != ".zip" else ""), extra=extra)
                return
        # Only known package assets can be served without a session token.
        asset_name = "index.html" if path == "/" else path.removeprefix("/assets/").removeprefix("/")
        if path == '/assets/typography.css':
            from .typography import stylesheet
            self._send(200, stylesheet(embedded=False), content_type='text/css; charset=utf-8')
            return
        if path.startswith('/assets/fonts/'):
            from .typography import FONT_FILES, FONT_DIR
            name = path.removeprefix('/assets/fonts/')
            if name in FONT_FILES:
                file = FONT_DIR / name
                if file.is_file() and not file.is_symlink():
                    self._send(200, file.read_bytes(), content_type='font/woff')
                    return
            self._send(404, {"error": "This resource is not available."})
            return
        if asset_name in {"index.html", "app.js", "model.js", "style.css", "styles.css", "gui.js", "favicon.svg", "report_view.js", "report_print.css"}:
            file = self.server.assets / asset_name
            if file.is_file() and not file.is_symlink():
                self._send(200, file.read_bytes(), content_type=(mimetypes.guess_type(file.name)[0] or "text/plain") + "; charset=utf-8")
                return
        self._send(404, {"error": "This resource is not available."})

    def do_POST(self):
        path = unquote(urlsplit(self.path).path)
        if not self._guard(api=True):
            return
        try:
            payload = self._body()
            if path == "/api/shutdown":
                self._send(200, {"status": "closing", "message": "The local application is closing. Saved analyses remain on this computer."})
                threading.Thread(target=self.server.shutdown, daemon=True).start()
                return
            if path in {"/api/validate", "/api/jobs"}:
                validation = validate_payload(payload)
                if path == "/api/validate":
                    self._send(200, validation)
                elif not validation["valid"]:
                    self._send(422, validation)
                else:
                    self._send(202, self.server.create_job(validation["payload"]))
                return
            match = re.fullmatch(r"/api/jobs/([A-Za-z0-9-]+)/cancel", path)
            if match and match[1] in self.server.jobs:
                self._send(200, self.server.cancel_job(match[1]))
                return
            self._send(404, {"error": "This action is not available."})
        except (ValueError, TypeError, KeyError, OverflowError, UnicodeError) as exc:
            self._send(400, {"error": str(exc)})
        except RuntimeError as exc:
            self._send(409, {"error": str(exc)})


def create_server(*, port=0, output_root=None, assets=None):
    """Create a loopback server; callers own its serving thread and shutdown."""
    return DesktopServer(port, output_root or _default_output_root(), assets or Path(__file__).parent / "gui_assets")


def start_gui(args=None):
    """Start the local interface; called by CLI and the portable desktop entry."""
    multiprocessing.freeze_support()
    if args is None:
        parser = argparse.ArgumentParser(description="Open the local MIC-50-90 interface.")
        parser.add_argument("--no-browser", action="store_true")
        parser.add_argument("--port", type=int, default=0)
        parser.add_argument("--output-root")
        parser.add_argument("--ready-file", help="Write local session details for controlled desktop checks.")
        args = parser.parse_args()
    server = create_server(port=getattr(args, "port", 0), output_root=getattr(args, "output_root", None))
    ready = getattr(args, "ready_file", None)
    if ready:
        target = Path(ready)
        target.parent.mkdir(parents=True, exist_ok=True)
        write_json(target, {"url": server.url, "token": server.token, "port": server.server_port, "pid": os.getpid()})
    if not getattr(args, "no_browser", False):
        webbrowser.open(server.url)
    print(f"MIC-50-90 {__version__}: local interface running at {server.origin}. Close this window to stop.", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
        if ready:
            Path(ready).unlink(missing_ok=True)
    return 0


def main():
    return start_gui()


if __name__ == "__main__":
    multiprocessing.freeze_support()
    raise SystemExit(main())
