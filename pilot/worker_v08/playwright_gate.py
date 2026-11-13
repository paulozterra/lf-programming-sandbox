#!/usr/bin/env python3
"""T5 trusted Worker browser acceptance: local backend + frontend + Chromium.

This is an ordinary AcceptanceCommand, so the existing verified Worker
runs it for either visible commands or an independent encrypted oracle.
No examiner material is read here. No model and no external browser traffic.
"""
from __future__ import annotations

import argparse
import ipaddress
import os
from pathlib import Path
import signal
import socket
import subprocess
import sys
import time
from urllib.parse import urlparse

# Fixed toolchain pin: installed only by trusted Worker CI, never by proposals.
PLAYWRIGHT_VERSION = "1.56.0"
BROWSERS_DIR = "/tmp/lf-playwright-browsers"
PYTHON_RUNTIME = Path("/tmp/lf-playwright-runtime/bin/python")
FRONTEND_PORT = 3000
BACKEND_PORT = 8080


class BrowserBlocked(RuntimeError):
    pass


def local_url(url: str) -> bool:
    try:
        parsed = urlparse(url)
        return (parsed.scheme in ("http", "https", "ws", "wss")
                and parsed.hostname in ("localhost", "127.0.0.1", "::1")
                and parsed.username is None and parsed.password is None
                and parsed.port in (FRONTEND_PORT, BACKEND_PORT))
    except ValueError:
        return False


def check_path(path: str) -> str:
    if (not isinstance(path, str) or not path.startswith("/")
            or path.startswith("//") or "\\" in path or "\r" in path or "\n" in path):
        raise BrowserBlocked("BROWSER_PATH_INVALID")
    return path


def available() -> None:
    """Fail closed before launching the app if the browser runtime is absent."""
    os.environ["PLAYWRIGHT_BROWSERS_PATH"] = BROWSERS_DIR
    try:
        from importlib.metadata import version
        if version("playwright") != PLAYWRIGHT_VERSION:
            raise BrowserBlocked("NAVEGADOR_NO_DISPONIBLE")
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            b = p.chromium.launch(headless=True)
            b.close()
    except BrowserBlocked:
        raise
    except Exception as exc:
        raise BrowserBlocked("NAVEGADOR_NO_DISPONIBLE") from exc


def _spawn(argv: list[str], root: Path) -> subprocess.Popen:
    try:
        # Neither browser assertions nor child-server logs receive secrets.
        return subprocess.Popen(argv, cwd=root, stdin=subprocess.DEVNULL,
                                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                start_new_session=True,
                                env={**os.environ, "CI": "true", "NEXT_TELEMETRY_DISABLED": "1"})
    except OSError as exc:
        raise BrowserBlocked("APP_NO_ARRANCA") from exc


def wait_local(port: int, proc: subprocess.Popen, seconds: int = 90) -> None:
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if proc.poll() is not None:
            raise BrowserBlocked("APP_NO_ARRANCA")
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.5):
                return
        except OSError:
            time.sleep(0.3)
    raise BrowserBlocked("APP_NO_ARRANCA")


def _stop(proc: subprocess.Popen) -> None:
    try:
        os.killpg(proc.pid, signal.SIGKILL)
    except ProcessLookupError:
        pass
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        pass


def verify(root: Path, *, path: str, selector: str, text: str | None,
           title: str | None, timeout_ms: int = 15000) -> None:
    path = check_path(path)
    if not root.is_dir() or not (root / "apps/time-service/pom.xml").is_file() \
            or not (root / "frontend/package.json").is_file():
        raise BrowserBlocked("APP_NO_ARRANCA")
    if not selector or len(selector) > 512 or timeout_ms < 1000 or timeout_ms > 30000:
        raise BrowserBlocked("BROWSER_CASE_INVALID")
    available()
    running = []
    try:
        backend = _spawn(["mvn", "-B", "-q", "-f", "apps/time-service/pom.xml",
                          "spring-boot:run", "-Dspring-boot.run.arguments=--server.address=127.0.0.1"],
                         root)
        running.append(backend)
        wait_local(BACKEND_PORT, backend)
        frontend = _spawn(["npm", "--prefix", "frontend", "run", "dev",
                           "--", "--hostname", "127.0.0.1", "--port", str(FRONTEND_PORT)], root)
        running.append(frontend)
        wait_local(FRONTEND_PORT, frontend)
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            try:
                browser = p.chromium.launch(headless=True)
            except Exception as exc:
                raise BrowserBlocked("NAVEGADOR_NO_DISPONIBLE") from exc
            try:
                context = browser.new_context(service_workers="block")
                # Network from Chromium never leaves the two loopback app ports.
                context.route("**/*", lambda route:
                              route.continue_() if local_url(route.request.url)
                              else route.abort("blockedbyclient"))
                context.route_web_socket("**/*", lambda ws:
                                         ws.connect() if local_url(ws.url)
                                         else ws.close())
                page = context.new_page()
                page.goto(f"http://127.0.0.1:{FRONTEND_PORT}{path}",
                          wait_until="domcontentloaded", timeout=timeout_ms)
                item = page.locator(selector).first
                item.wait_for(state="visible", timeout=timeout_ms)
                if text is not None and text not in item.inner_text(timeout=timeout_ms):
                    raise BrowserBlocked("BROWSER_ASSERTION_FAILED")
                if title is not None and title not in page.title():
                    raise BrowserBlocked("BROWSER_ASSERTION_FAILED")
                context.close()
            finally:
                browser.close()
    except BrowserBlocked:
        raise
    except Exception as exc:
        raise BrowserBlocked("BROWSER_ASSERTION_FAILED") from exc
    finally:
        for proc in reversed(running):
            _stop(proc)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path("."))
    parser.add_argument("--path", default="/")
    parser.add_argument("--selector", required=True)
    parser.add_argument("--text")
    parser.add_argument("--title")
    parser.add_argument("--timeout-ms", type=int, default=15000)
    args = parser.parse_args()
    try:
        verify(args.root, path=args.path, selector=args.selector,
               text=args.text, title=args.title, timeout_ms=args.timeout_ms)
    except BrowserBlocked as exc:
        print(str(exc).split(":")[0], file=sys.stderr)
        return 1
    print("BROWSER_VISIBLE_CHECK_PASS")
    return 0


if __name__ == "__main__":
    # Vendored command execution intentionally strips the runner's PATH.
    # Re-exec in the trusted pinned Python venv, not whichever python3 is
    # installed in /usr/local/bin or selected by a proposal.
    if not PYTHON_RUNTIME.is_file():
        print("NAVEGADOR_NO_DISPONIBLE", file=sys.stderr)
        raise SystemExit(1)
    try:
        if Path(sys.executable).absolute() != PYTHON_RUNTIME.absolute():
            os.execv(str(PYTHON_RUNTIME), [str(PYTHON_RUNTIME), __file__, *sys.argv[1:]])
    except OSError:
        print("NAVEGADOR_NO_DISPONIBLE", file=sys.stderr)
        raise SystemExit(1)
    raise SystemExit(main())
