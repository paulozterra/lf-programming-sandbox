#!/usr/bin/env python3
"""T5 trusted Worker browser acceptance: local backend + frontend + Chromium.

This is an ordinary AcceptanceCommand, so the existing verified Worker
runs it for either visible commands or an independent encrypted oracle.
No examiner material is read here. No model and no external browser traffic.
"""
from __future__ import annotations
import sys as _project_sys
from pathlib import Path as _project_Path
_project_sys.path.insert(0, str(_project_Path(__file__).resolve().parents[2]))

import argparse
import json
import re
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
PYTHON_RUNTIME = Path("/tmp/lf-python-runtime/bin/python")
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


CASE_KEYS = {"id", "path", "selector", "text", "title", "count", "css", "box",
             "viewport"}
BOX_KEYS = {"width", "height", "tolerance_px"}
CSS_PROPERTY = re.compile(r"[a-z-]{1,48}\Z")
CASE_ID = re.compile(r"[A-Za-z0-9_.-]{1,96}\Z")
MAX_CASES = 200


def _number(value, low, high):
    return (type(value) in (int, float) and low <= value <= high)


def check_case(case) -> dict:
    """Declarative browser case: data only, never code. Unknown keys deny."""
    if not isinstance(case, dict) or not set(case) <= CASE_KEYS:
        raise BrowserBlocked("BROWSER_CASE_INVALID")
    if not isinstance(case.get("id"), str) or not CASE_ID.fullmatch(case["id"]):
        raise BrowserBlocked("BROWSER_CASE_INVALID")
    check_path(case.get("path", "/"))
    selector = case.get("selector")
    if not isinstance(selector, str) or not selector or len(selector) > 512:
        raise BrowserBlocked("BROWSER_CASE_INVALID")
    for key in ("text", "title"):
        if key in case and (not isinstance(case[key], str) or not case[key]
                            or len(case[key]) > 512):
            raise BrowserBlocked("BROWSER_CASE_INVALID")
    if "count" in case and not (type(case["count"]) is int and 0 <= case["count"] <= 500):
        raise BrowserBlocked("BROWSER_CASE_INVALID")
    css = case.get("css", {})
    if (not isinstance(css, dict) or len(css) > 24
            or any(not isinstance(k, str) or not CSS_PROPERTY.fullmatch(k)
                   or not isinstance(v, str) or not v or len(v) > 128
                   for k, v in css.items())):
        raise BrowserBlocked("BROWSER_CASE_INVALID")
    box = case.get("box", {})
    if (not isinstance(box, dict) or not set(box) <= BOX_KEYS
            or any(k in box and not _number(box[k], 0, 10000) for k in ("width", "height"))
            or ("tolerance_px" in box and not _number(box["tolerance_px"], 0, 50))):
        raise BrowserBlocked("BROWSER_CASE_INVALID")
    if not any(k in case for k in ("text", "title", "count")) and not css and not box:
        # Visibility alone does not characterize behavior.
        raise BrowserBlocked("BROWSER_CASE_WITHOUT_ASSERTION")
    viewport = case.get("viewport")
    if viewport is not None and (not isinstance(viewport, dict)
                                 or set(viewport) != {"width", "height"}
                                 or not all(type(viewport[k]) is int and 200 <= viewport[k] <= 4000
                                            for k in viewport)):
        raise BrowserBlocked("BROWSER_CASE_INVALID")
    return case


def load_suite(root: Path, suite: str) -> list[dict]:
    """All *.json case files of a repository-relative suite directory."""
    rel = Path(suite)
    if rel.is_absolute() or ".." in rel.parts:
        raise BrowserBlocked("BROWSER_SUITE_INVALID")
    folder = root / rel
    if folder.is_symlink() or (folder.exists() and not folder.is_dir()):
        raise BrowserBlocked("BROWSER_SUITE_INVALID")
    cases, seen = [], set()
    for file in sorted(folder.glob("*.json")) if folder.is_dir() else []:
        if file.is_symlink() or not file.is_file():
            raise BrowserBlocked("BROWSER_SUITE_INVALID")
        try:
            data = json.loads(file.read_text("utf-8"))
        except (OSError, ValueError) as exc:
            raise BrowserBlocked("BROWSER_SUITE_INVALID") from exc
        items = data.get("cases") if isinstance(data, dict) else None
        if not isinstance(items, list) or not items or set(data) - {"cases", "covers"}:
            raise BrowserBlocked("BROWSER_SUITE_INVALID")
        for case in items:
            check_case(case)
            if case["id"] in seen:
                raise BrowserBlocked("BROWSER_SUITE_INVALID")
            seen.add(case["id"])
            cases.append(case)
    if len(cases) > MAX_CASES:
        raise BrowserBlocked("BROWSER_SUITE_INVALID")
    return cases


def assert_case(page, case: dict, timeout_ms: int) -> None:
    if case.get("viewport"):
        page.set_viewport_size(case["viewport"])
    page.goto(f"http://127.0.0.1:{FRONTEND_PORT}{case.get('path', '/')}",
              wait_until="domcontentloaded", timeout=timeout_ms)
    found = page.locator(case["selector"])
    if "count" in case:
        if case["count"] == 0:
            if found.count() != 0:
                raise BrowserBlocked("BROWSER_ASSERTION_FAILED:" + case["id"])
            return
        found.first.wait_for(state="attached", timeout=timeout_ms)
        if found.count() != case["count"]:
            raise BrowserBlocked("BROWSER_ASSERTION_FAILED:" + case["id"])
    item = found.first
    item.wait_for(state="visible", timeout=timeout_ms)
    _assert_loaded(page, case, item, timeout_ms)


def _assert_loaded(page, case: dict, item, timeout_ms: int) -> None:
    if "text" in case and case["text"] not in item.inner_text(timeout=timeout_ms):
        raise BrowserBlocked("BROWSER_ASSERTION_FAILED:" + case["id"])
    if "title" in case and case["title"] not in page.title():
        raise BrowserBlocked("BROWSER_ASSERTION_FAILED:" + case["id"])
    for prop, want in case.get("css", {}).items():
        got = item.evaluate("(el, p) => getComputedStyle(el).getPropertyValue(p)", prop)
        if str(got).strip() != want:
            raise BrowserBlocked("BROWSER_ASSERTION_FAILED:" + case["id"])
    box = case.get("box")
    if box:
        rect = item.bounding_box()
        tol = box.get("tolerance_px", 1)
        if rect is None or any(abs(rect[k] - box[k]) > tol for k in ("width", "height") if k in box):
            raise BrowserBlocked("BROWSER_ASSERTION_FAILED:" + case["id"])


# Applies the first candidate value that really changes the computed style;
# returns false if none does (the assertion then cannot be proven to matter).
MUTATION_JS = """(el, m) => {
  for (const [prop, candidates] of Object.entries(m)) {
    const before = getComputedStyle(el).getPropertyValue(prop);
    let changed = false;
    for (const value of candidates) {
      el.style.setProperty(prop, value, 'important');
      if (getComputedStyle(el).getPropertyValue(prop) !== before) { changed = true; break; }
    }
    if (!changed) return false;
  }
  return true;
}"""
CSS_CANDIDATES = ("777px", "rgb(1, 2, 3)", "none", "block", "inline", "hidden",
                  "0.37", "italic", "900", "100", "line-through", "uppercase",
                  "center", "right", "column", "wrap", "space-between", "3", "fixed")


def mutations(case: dict) -> list[dict]:
    """Mechanical in-page mutations of each asserted CSS value and box size.
    A discriminating case must fail under every one of them."""
    result = [{prop: list(CSS_CANDIDATES)} for prop in case.get("css", {})]
    box = case.get("box", {})
    for key in ("width", "height"):
        if key in box:
            target = f"{max(1, round(box[key] * 1.25 + 10 + 2 * box.get('tolerance_px', 1)))}px"
            result.append({key: [target],
                           "min-" + key: [target], "max-" + key: [target]})
    return result


def discriminates(page, case: dict, timeout_ms: int) -> None:
    """Re-run a passing case under each mutation; it must fail every time."""
    for mutation in mutations(case):
        page.goto(f"http://127.0.0.1:{FRONTEND_PORT}{case.get('path', '/')}",
                  wait_until="domcontentloaded", timeout=timeout_ms)
        item = page.locator(case["selector"]).first
        item.wait_for(state="visible", timeout=timeout_ms)
        if not item.evaluate(MUTATION_JS, mutation):
            raise BrowserBlocked("BROWSER_CASE_NOT_MUTABLE:" + case["id"])
        try:
            _assert_loaded(page, case, item, timeout_ms)
        except BrowserBlocked:
            continue
        raise BrowserBlocked("BROWSER_CASE_NOT_DISCRIMINATING:" + case["id"])


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
    import tempfile
    log = None
    try:
        log = tempfile.TemporaryFile()
        proc = subprocess.Popen(argv, cwd=root, stdin=subprocess.DEVNULL,
                                stdout=log, stderr=subprocess.STDOUT,
                                start_new_session=True,
                                env={**os.environ, "CI": "true", "NEXT_TELEMETRY_DISABLED": "1"})
        proc._lf_log = log  # type: ignore[attr-defined]
        return proc
    except OSError as exc:
        if log is not None:
            log.close()
        print("APP_NO_ARRANCA_DETALLE: SPAWN_FAILED", file=sys.stderr)
        raise BrowserBlocked("APP_NO_ARRANCA") from exc


# Emit only fixed diagnostic categories, never arbitrary child-controlled text.
# pread avoids altering the shared write offset while the process is alive.
_DIAG_TAIL_BYTES = 64 * 1024
_DIAG_PATTERNS = (
    ("MAVEN_DEPENDENCY_TRANSFER", rb"downloading (?:from |spring-boot-maven-plugin)|could not (?:transfer|resolve)|non-resolvable parent pom"),
    ("DATABASE_CONNECTION", rb"connection refused|failed to obtain jdbc connection|unable to obtain connection from database"),
    ("PORT_IN_USE", rb"address already in use|port [0-9]+ was already in use|eaddrinuse"),
    ("JAVA_START_FAILURE", rb"application failed to start|could not find or load main class|unsupportedclassversionerror"),
    ("NODE_START_FAILURE", rb"cannot find module|module not found|next: not found"),
)


def _start_diagnosis(name: str, proc: subprocess.Popen, seconds: int) -> None:
    code = proc.poll()
    cause = f"TIMEOUT_{seconds}S" if code is None else f"EXIT_{code}"
    print(f"APP_NO_ARRANCA_DETALLE: {name} {cause}", file=sys.stderr)
    log = getattr(proc, "_lf_log", None)
    if log is None:
        return
    try:
        size = os.fstat(log.fileno()).st_size
        raw = os.pread(log.fileno(), min(size, _DIAG_TAIL_BYTES),
                       max(0, size - _DIAG_TAIL_BYTES)).lower()
    except (OSError, ValueError):
        return
    for category, pattern in _DIAG_PATTERNS:
        if re.search(pattern, raw):
            print(f"APP_NO_ARRANCA_INDICIO: {name} {category}", file=sys.stderr)


def wait_local(port: int, proc: subprocess.Popen, seconds: int = 90, name: str = "APP") -> None:
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if proc.poll() is not None:
            _start_diagnosis(name, proc, seconds)
            raise BrowserBlocked("APP_NO_ARRANCA")
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.5):
                return
        except OSError:
            time.sleep(0.3)
    _start_diagnosis(name, proc, seconds)
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
    finally:
        log = getattr(proc, "_lf_log", None)
        if log is not None:
            log.close()


APP_START_ATTEMPTS = 2


def verify(root: Path, **kwargs) -> None:
    """Retry only when the local app did not start (a known runner flake);
    never retry a failing browser assertion."""
    for attempt in range(1, APP_START_ATTEMPTS + 1):
        try:
            return _verify_once(root, **kwargs)
        except BrowserBlocked as exc:
            if str(exc) != "APP_NO_ARRANCA" or attempt == APP_START_ATTEMPTS:
                raise
            print("APP_NO_ARRANCA: reintento de arranque " + str(attempt + 1), file=sys.stderr)
            time.sleep(5)


def _verify_once(root: Path, *, path: str, selector: str, text: str | None,
           title: str | None, timeout_ms: int = 15000, cases: list | None = None,
           mutate: bool = False) -> None:
    path = check_path(path)
    from pilot.config import project_config as _project
    pom = _project.area_component("BACKEND", "maven")["build_file"]
    web = _project.area_component("FRONTEND", "npm")
    if not root.is_dir() or not (root / pom).is_file() \
            or not (root / web["build_file"]).is_file():
        raise BrowserBlocked("APP_NO_ARRANCA")
    if not selector or len(selector) > 512 or timeout_ms < 1000 or timeout_ms > 30000:
        raise BrowserBlocked("BROWSER_CASE_INVALID")
    available()
    running = []
    try:
        backend = _spawn(["mvn", "-B", "-q", "-f", pom,
                          "spring-boot:run", "-Dspring-boot.run.arguments=--server.address=127.0.0.1"],
                         root)
        running.append(backend)
        wait_local(BACKEND_PORT, backend, name="BACKEND")
        frontend = _spawn(["npm", "--prefix", web["root"], "run", "dev",
                           "--", "--hostname", "127.0.0.1", "--port", str(FRONTEND_PORT)], root)
        running.append(frontend)
        wait_local(FRONTEND_PORT, frontend, name="FRONTEND")
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
                                         ws.connect_to_server() if local_url(ws.url)
                                         else ws.close())
                page = context.new_page()
                if cases is not None:
                    for case in cases:
                        assert_case(page, case, timeout_ms)
                        if mutate and (case.get("css") or case.get("box")):
                            discriminates(page, case, timeout_ms)
                    context.close()
                    return
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
    parser.add_argument("--selector")
    parser.add_argument("--suite", help="repository-relative folder of *.json cases")
    parser.add_argument("--mutation-check", action="store_true",
                        help="each css/box case must fail under in-page mutations")
    parser.add_argument("--text")
    parser.add_argument("--title")
    parser.add_argument("--timeout-ms", type=int, default=15000)
    args = parser.parse_args()
    try:
        if args.suite is not None:
            cases = load_suite(args.root, args.suite)
            if not cases:
                print("BROWSER_SUITE_NO_CASES")
                return 0
            verify(args.root, path="/", selector="body", text=None, title=None,
                   timeout_ms=args.timeout_ms, cases=cases, mutate=args.mutation_check)
            print("BROWSER_SUITE_PASS:" + str(len(cases)))
            return 0
        if not args.selector:
            raise BrowserBlocked("BROWSER_CASE_INVALID")
        verify(args.root, path=args.path, selector=args.selector,
               text=args.text, title=args.title, timeout_ms=args.timeout_ms)
    except BrowserBlocked as exc:
        # The failing case id is safe to show: it is visible repository data.
        print(str(exc), file=sys.stderr)
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
