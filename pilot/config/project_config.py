"""T54 phase 1: validated, explicit per-project paths. No consumers yet.

All paths are repository-relative; a project config never authorizes a path
outside its declared write roots. Existing symlinks in any path ancestor deny.
"""
from __future__ import annotations

import json
import re
from pathlib import Path, PurePosixPath
from collections.abc import Mapping, Set as AbcSet

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
# T54 phase 3a: components are an open map (a project may have no frontend,
# or several services). Every component declares the same complete shape;
# optional facts are explicit null / [] rather than absent keys.
COMPONENT_KEYS = frozenset({
    "kind", "root", "build_file", "lock_file", "source_roots", "resource_roots",
    "test_roots", "migrations_root", "config_files", "generated_client",
})
COMPONENT_KINDS = frozenset({"maven", "npm"})
COMPONENT_NAME = re.compile(r"[a-z][a-z0-9_-]{0,31}\Z")
GENERATED_CLIENT_KEYS = frozenset({"dir", "script", "generator"})
NPM_SCRIPT = re.compile(r"[a-z][a-z0-9:_-]{0,63}\Z")
# Lot areas are route vocabulary (CP3.x); their roots are project facts.
AREA_ORDER = ("CONTRATO", "INFRA", "DATA", "BACKEND", "FRONTEND")
AREAS = frozenset(AREA_ORDER)
# Control-plane protections are a route invariant, not a project choice: no
# project configuration may omit or lift them (review of PR #361, H1/H5).
CONTROL_PLANE_PROTECTED = (".github/**", ".lf/**", "pilot/**", "vendor/**")
AREA_KEYS = frozenset({"write_prefixes", "project_roots"})
LOT_POLICY_AREA_KEYS = frozenset({"unprotect", "unprotect_if_written", "protect", "context_files"})
REQUIRED_TOP = frozenset({
    "schema_version", "project_id", "storage", "components", "areas",
    "lot_policy", "protected_paths", "write_roots",
})
SCHEMA_VERSION = "LF_PROJECT_CONFIG_V2"


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


def _optional_path(value: object, root: Path, parent: str) -> str | None:
    if value is None:
        return None
    path = _path(value, root)
    if not _within(path, parent):
        _deny()
    return path


def _list_within(value: object, root: Path, parent: str, *, allow_empty: bool) -> list[str]:
    if type(value) is not list or (not value and not allow_empty):
        _deny()
    paths = [_path(v, root) for v in value]
    if len(paths) != len(set(paths)) or any(not _within(p, parent) for p in paths):
        _deny()
    return paths


def _component(item: object, root: Path) -> str:
    item = _object(item, COMPONENT_KEYS)
    if item["kind"] not in COMPONENT_KINDS:
        _deny()
    base = _path(item["root"], root)
    if not _within(_path(item["build_file"], root), base):
        _deny()
    _optional_path(item["lock_file"], root, base)
    _list_within(item["source_roots"], root, base, allow_empty=False)
    _list_within(item["resource_roots"], root, base, allow_empty=True)
    _list_within(item["test_roots"], root, base, allow_empty=True)
    _optional_path(item["migrations_root"], root, base)
    _list_within(item["config_files"], root, base, allow_empty=True)
    client = item["generated_client"]
    if client is not None:
        client = _object(client, GENERATED_CLIENT_KEYS)
        _optional_path(client["dir"], root, base)
        _optional_path(client["generator"], root, base)
        if not isinstance(client["script"], str) or not NPM_SCRIPT.fullmatch(client["script"]):
            _deny()
        if item["kind"] != "npm":
            _deny()
    return base


def _prefix(value: object, root: Path) -> str:
    if not isinstance(value, str) or not value.endswith("/"):
        _deny()
    _path(value[:-1], root)
    return value


def _areas(value: object, root: Path) -> None:
    if type(value) is not dict or set(value) != AREAS:
        _deny()
    for area in value.values():
        area = _object(area, AREA_KEYS)
        for key in AREA_KEYS:
            prefixes = area[key]
            if type(prefixes) is not list or not prefixes:
                _deny()
            checked = [_prefix(v, root) for v in prefixes]
            if len(checked) != len(set(checked)):
                _deny()


def _lot_policy(value: object, root: Path) -> None:
    """Per-area protection of generated lot templates (T54 phase 3b).

    protected_base applies to every lot; an area may only unprotect entries of
    the base (never invent a hole), and add globs or exact context files.
    """
    value = _object(value, frozenset({"protected_base", "areas"}))
    base = _paths(value["protected_base"], root, glob=True)
    if not set(CONTROL_PLANE_PROTECTED) <= set(base):
        _deny()
    areas = value["areas"]
    if type(areas) is not dict or set(areas) != AREAS:
        _deny()
    for area in areas.values():
        area = _object(area, LOT_POLICY_AREA_KEYS)
        for key in LOT_POLICY_AREA_KEYS:
            if type(area[key]) is not list:
                _deny()
            checked = [_path(v, root, glob=key != "context_files") for v in area[key]]
            if len(checked) != len(set(checked)):
                _deny()
        lifted = set(area["unprotect"]) | set(area["unprotect_if_written"])
        if not lifted <= set(base) or lifted & set(CONTROL_PLANE_PROTECTED):
            _deny()
        if set(area["unprotect"]) & set(area["unprotect_if_written"]):
            _deny()


def validate(data: object, *, root: Path = ROOT, project: str | None = None) -> dict:
    """Validate the complete schema, including explicit write boundaries."""
    root = Path(root)
    obj = _object(data, REQUIRED_TOP)
    if obj["schema_version"] != SCHEMA_VERSION:
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
    components = obj["components"]
    if type(components) is not dict or not components:
        _deny()
    component_roots = []
    for name, item in components.items():
        if not isinstance(name, str) or not COMPONENT_NAME.fullmatch(name):
            _deny()
        component_roots.append(_component(item, root))
    if len(set(component_roots)) != len(component_roots):
        _deny()
    _areas(obj["areas"], root)
    _lot_policy(obj["lot_policy"], root)
    _paths(obj["protected_paths"], root, glob=True)
    write_roots = _paths(obj["write_roots"], root)
    # Every storage and component root must have explicit write authorization.
    for path in [storage[k] for k in REQUIRED_STORAGE - {"task_template_pattern"}] + component_roots:
        if not any(_within(path, allowed) for allowed in write_roots):
            _deny()
    # Area project roots are writable product roots; a coarse write prefix
    # ("apps/") must at least contain an authorized root.
    for area in obj["areas"].values():
        for prefix in area["project_roots"]:
            if not any(_within(prefix.rstrip("/"), allowed) for allowed in write_roots):
                _deny()
        for prefix in area["write_prefixes"]:
            bare = prefix.rstrip("/")
            if not any(_within(bare, allowed) or _within(allowed, bare)
                       for allowed in write_roots):
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

# The repository whose pilot/config/ defines the active project (patchable in tests).
CONFIG_ROOT = ROOT

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
    """Read storage from the configuration repository `root`; no implicit project."""
    name = active_project(root=root) if project is None else project
    return load(name, root=root)["storage"]


def repo_storage(project: str | None = None) -> dict[str, str]:
    """Configuration always comes from the repository holding this code.

    A data root (e.g. --root "$RUNNER_TEMP" for Analysis F0/F5, or a test's
    tmp_path) only says where files live; it never supplies configuration.
    Reading config from the data root made every scratch-dir caller fail
    (T54 fase 2b). Tests that need another config patch CONFIG_ROOT.
    """
    return storage(root=CONFIG_ROOT, project=project)


def storage_path(kind: str, *parts: str, root: Path = ROOT,
                 project: str | None = None) -> Path:
    """Resolve a declared storage root under the data `root`."""
    cfg = repo_storage(project)
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
    template = repo_storage(project)["task_template_pattern"]
    escaped = re.escape(template)
    escaped = escaped.replace(re.escape("{request}"), re.escape(request))
    escaped = escaped.replace(re.escape("{task}"), r"[a-z][a-z0-9_-]{0,31}")
    return re.compile(escaped + r"\Z")


def template_path_any_request(*, root: Path = ROOT,
                              project: str | None = None) -> re.Pattern[str]:
    """Strict Worker template regex for any valid issue request."""
    template = repo_storage(project)["task_template_pattern"]
    escaped = re.escape(template)
    escaped = escaped.replace(re.escape("{request}"), r"req-[1-9][0-9]*")
    escaped = escaped.replace(re.escape("{task}"), r"[a-z][a-z0-9_-]{0,31}")
    return re.compile(escaped + r"\Z")


def request_context_pattern(*, root: Path = ROOT,
                            project: str | None = None) -> re.Pattern[str]:
    """Strict request path prefix used by integration and reuse guards."""
    prefix = re.escape(repo_storage(project)["requests_root"])
    return re.compile(prefix + r"/(req-[1-9][0-9]*)/")


def reuse_assessment_pattern(*, root: Path = ROOT,
                             project: str | None = None) -> re.Pattern[str]:
    prefix = re.escape(repo_storage(project)["requests_root"])
    return re.compile(prefix + r"/[a-z][a-z0-9_-]{0,63}/reuse_assessment[.]json\Z")


# T54 phase 3a accessors: configuration always from the code repository.
def _repo_config(project: str | None = None) -> dict:
    name = active_project(root=CONFIG_ROOT) if project is None else project
    return load(name, root=CONFIG_ROOT)


def components(project: str | None = None) -> dict[str, dict]:
    return _repo_config(project)["components"]


def component(name: str, project: str | None = None) -> dict:
    found = components(project).get(name)
    if found is None:
        _deny()
    return found


def area_write_prefixes(area: str, project: str | None = None) -> tuple[str, ...]:
    if area not in AREAS:
        _deny()
    return tuple(_repo_config(project)["areas"][area]["write_prefixes"])


def area_project_roots(area: str, project: str | None = None) -> tuple[str, ...]:
    if area not in AREAS:
        _deny()
    return tuple(_repo_config(project)["areas"][area]["project_roots"])


def protected_paths(project: str | None = None) -> tuple[str, ...]:
    return tuple(_repo_config(project)["protected_paths"])


def all_test_roots(project: str | None = None) -> tuple[str, ...]:
    roots: list[str] = []
    for item in components(project).values():
        roots.extend(item["test_roots"])
    return tuple(roots)


def lot_policy(project: str | None = None) -> dict:
    return _repo_config(project)["lot_policy"]


def area_components(area: str, project: str | None = None) -> list[tuple[str, dict]]:
    """Components that own any project root of the area, sorted by name."""
    roots = area_project_roots(area, project)
    found = []
    for name, item in sorted(components(project).items()):
        if any(_within(r.rstrip("/"), item["root"]) for r in roots):
            found.append((name, item))
    return found


def area_component(area: str, kind: str, project: str | None = None) -> dict:
    """The single component of `kind` serving `area`; anything else denies."""
    matches = [item for _, item in area_components(area, project) if item["kind"] == kind]
    if len(matches) != 1:
        _deny()
    return matches[0]


def product_top_dirs(project: str | None = None) -> tuple[str, ...]:
    """Top-level directories of every area write prefix, e.g. ("apps/", "db/")."""
    tops = []
    for area in sorted(AREAS):
        for prefix in area_write_prefixes(area, project):
            top = prefix.split("/", 1)[0] + "/"
            if top not in tops:
                tops.append(top)
    return tuple(tops)


class AreaTable(Mapping):
    """Read-only area -> roots table resolved on every access (never at import).

    Importing a consumer needs no configuration; an operation that reads a
    root resolves the *current* active project, fail-closed.
    """

    def __init__(self, resolve):
        self._resolve = resolve

    def __getitem__(self, area):
        if area not in AREAS:
            raise KeyError(area)
        return self._resolve(area)

    def __iter__(self):
        return iter(AREA_ORDER)

    def __len__(self):
        return len(AREA_ORDER)

    def __eq__(self, other):
        return isinstance(other, Mapping) and dict(self.items()) == dict(other.items())

    __hash__ = None


class ProductRoots(AbcSet):
    """Every area write prefix of the current project, resolved on access."""

    def _values(self):
        roots = []
        for area in AREA_ORDER:
            for prefix in area_write_prefixes(area):
                if prefix not in roots:
                    roots.append(prefix)
        return roots

    def __contains__(self, value):
        return value in self._values()

    def __iter__(self):
        return iter(self._values())

    def __len__(self):
        return len(self._values())
