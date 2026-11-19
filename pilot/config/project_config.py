"""T54 phase 1: validated, explicit per-project paths. No consumers yet.

All paths are repository-relative; a project config never authorizes a path
outside its declared write roots. Existing symlinks in any path ancestor deny.
"""
from __future__ import annotations

import json
import re
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parents[2]
CONFIG_DIR = "pilot/config/projects"
PROJECT_ID = re.compile(r"[a-z][a-z0-9_-]{0,31}\Z")
PART = re.compile(r"[A-Za-z0-9._-]+\Z")
TEMPLATE = re.compile(
    r"(?P<root>[A-Za-z0-9._/-]+)/\{request\}/templates/\{task\}\.task\.json\Z"
)
REQUIRED_STORAGE = frozenset({
    "requests_root", "registrations_root", "chain_plans_root",
    "task_template_pattern",
})
REQUIRED_COMPONENTS = {
    "backend": frozenset({"root", "build_file", "test_roots"}),
    "frontend": frozenset({"root", "manifest", "test_roots"}),
}
REQUIRED_TOP = frozenset({
    "schema_version", "project_id", "storage", "components",
    "protected_paths", "write_roots",
})


class ProjectConfigError(ValueError):
    """Configuration is missing, unsafe or inconsistent."""


def _deny() -> None:
    raise ProjectConfigError("PROJECT_CONFIG_INVALID")


def _object(value: object, keys: frozenset[str]) -> dict:
    if type(value) is not dict or set(value) != keys:
        _deny()
    return value


def _path(value: object, root: Path, *, glob: bool = False) -> str:
    if not isinstance(value, str) or not value or "\\" in value or value.startswith("/"):
        _deny()
    if "//" in value or value.endswith("/") or ":" in value or "\x00" in value:
        _deny()
    parts = value.split("/")
    if any(p in ("", ".", "..") for p in parts):
        _deny()
    for p in parts:
        if glob:
            # Only a complete glob segment or a __tests__-style name is allowed.
            if p in ("*", "**"):
                continue
        if not PART.fullmatch(p):
            _deny()
    # Do not follow any symlink, including ancestors of a path that does not
    # exist yet. Path.resolve() alone would conceal the link.
    cursor = root
    for part in parts:
        if part in ("*", "**"):
            break
        cursor = cursor / part
        if cursor.is_symlink():
            _deny()
    return value


def _paths(value: object, root: Path, *, glob: bool = False) -> list[str]:
    if type(value) is not list or not value:
        _deny()
    paths = [_path(v, root, glob=glob) for v in value]
    if len(paths) != len(set(paths)):
        _deny()
    return paths


def _within(path: str, parent: str) -> bool:
    return path == parent or path.startswith(parent + "/")


def validate(data: object, *, root: Path = ROOT, project: str | None = None) -> dict:
    """Validate the complete v1 schema, including explicit write boundaries."""
    root = Path(root)
    obj = _object(data, REQUIRED_TOP)
    if obj["schema_version"] != "LF_PROJECT_CONFIG_V1":
        _deny()
    name = obj["project_id"]
    if not isinstance(name, str) or not PROJECT_ID.fullmatch(name):
        _deny()
    if project is not None and name != project:
        _deny()
    storage = _object(obj["storage"], REQUIRED_STORAGE)
    for key in REQUIRED_STORAGE - {"task_template_pattern"}:
        _path(storage[key], root)
    pattern = storage["task_template_pattern"]
    if not isinstance(pattern, str):
        _deny()
    match = TEMPLATE.fullmatch(pattern)
    if match is None or match["root"] != storage["requests_root"]:
        _deny()
    _path(match["root"] + "/req-1/templates/example.task.json", root)
    components = _object(obj["components"], frozenset(REQUIRED_COMPONENTS))
    for component, required in REQUIRED_COMPONENTS.items():
        item = _object(components[component], required)
        component_root = _path(item["root"], root)
        for key in required - {"root", "test_roots"}:
            path = _path(item[key], root)
            if not _within(path, component_root):
                _deny()
        for path in _paths(item["test_roots"], root):
            if not _within(path, component_root):
                _deny()
    _paths(obj["protected_paths"], root, glob=True)
    write_roots = _paths(obj["write_roots"], root)
    # Every storage and component root must have explicit write authorization.
    for path in [storage[k] for k in REQUIRED_STORAGE - {"task_template_pattern"}] + [
        components[k]["root"] for k in REQUIRED_COMPONENTS
    ]:
        if not any(_within(path, allowed) for allowed in write_roots):
            _deny()
    return obj


def load(project: str, *, root: Path = ROOT) -> dict:
    """Load one explicitly named project; never fall back to sandbox defaults."""
    if not isinstance(project, str) or not PROJECT_ID.fullmatch(project):
        _deny()
    root = Path(root)
    path = root / CONFIG_DIR / (project + ".json")
    # Check config file and all existing ancestors for symlinks.
    _path(CONFIG_DIR + "/" + project + ".json", root)
    if not path.is_file():
        _deny()
    try:
        return validate(json.loads(path.read_text(encoding="utf-8")),
                        root=root, project=project)
    except (OSError, UnicodeError, ValueError, TypeError, RecursionError) as exc:
        if isinstance(exc, ProjectConfigError):
            raise
        _deny()

# T54 phase 2b: active project is explicit and validated; no sandbox default.
ACTIVE_PROJECT_PATH = "pilot/config/active_project.json"


def active_project(*, root: Path = ROOT) -> str:
    root = Path(root)
    _path(ACTIVE_PROJECT_PATH, root)
    file = root / ACTIVE_PROJECT_PATH
    if not file.is_file():
        _deny()
    try:
        obj = json.loads(file.read_text(encoding="utf-8"))
        _object(obj, frozenset({"schema_version", "project_id"}))
        if obj["schema_version"] != "LF_ACTIVE_PROJECT_V1":
            _deny()
        name = obj["project_id"]
        if not isinstance(name, str) or not PROJECT_ID.fullmatch(name):
            _deny()
        load(name, root=root)
        return name
    except (OSError, UnicodeError, ValueError, TypeError) as exc:
        if isinstance(exc, ProjectConfigError):
            raise
        _deny()


def storage(*, root: Path = ROOT, project: str | None = None) -> dict[str, str]:
    """Read storage from the requested root; no implicit sandbox project."""
    name = active_project(root=root) if project is None else project
    return load(name, root=root)["storage"]


def storage_path(kind: str, *parts: str, root: Path = ROOT,
                 project: str | None = None) -> Path:
    """Resolve only declared roots, from configuration at the given root."""
    cfg = storage(root=root, project=project)
    if kind not in ("requests_root", "registrations_root", "chain_plans_root"):
        _deny()
    for part in parts:
        if not isinstance(part, str) or not PART.fullmatch(part) or part in (".", ".."):
            _deny()
    return Path(root) / cfg[kind] / Path(*parts)


def template_path_pattern(request: str, *, root: Path = ROOT,
                          project: str | None = None) -> re.Pattern[str]:
    """Match exactly one request and one task from validated template contract."""
    if not isinstance(request, str) or not re.fullmatch(r"req-[1-9][0-9]*", request):
        _deny()
    template = storage(root=root, project=project)["task_template_pattern"]
    escaped = re.escape(template)
    escaped = escaped.replace(re.escape("{request}"), re.escape(request))
    escaped = escaped.replace(re.escape("{task}"), r"[a-z][a-z0-9_-]{0,31}")
    return re.compile(escaped + r"\\Z")


def template_path_any_request(*, root: Path = ROOT,
                              project: str | None = None) -> re.Pattern[str]:
    """Strict Worker template regex for any valid issue request."""
    template = storage(root=root, project=project)["task_template_pattern"]
    escaped = re.escape(template)
    escaped = escaped.replace(re.escape("{request}"), r"req-[1-9][0-9]*")
    escaped = escaped.replace(re.escape("{task}"), r"[a-z][a-z0-9_-]{0,31}")
    return re.compile(escaped + r"\\Z")


def request_context_pattern(*, root: Path = ROOT,
                            project: str | None = None) -> re.Pattern[str]:
    """Strict request path prefix used by integration and reuse guards."""
    prefix = re.escape(storage(root=root, project=project)["requests_root"])
    return re.compile(prefix + r"/(req-[1-9][0-9]*)/")


def reuse_assessment_pattern(*, root: Path = ROOT,
                             project: str | None = None) -> re.Pattern[str]:
    prefix = re.escape(storage(root=root, project=project)["requests_root"])
    return re.compile(prefix + r"/[a-z][a-z0-9_-]{0,63}/reuse_assessment[.]json\\Z")
