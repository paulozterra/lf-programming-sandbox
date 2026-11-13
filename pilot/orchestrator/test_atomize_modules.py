"""T1: scope-base module identities and syntax-safe generated paths."""
import re

import pytest

from pilot.orchestrator import atomize


@pytest.mark.parametrize(("scope", "expected"), [
    ("SBX-AUTH-LOGIN-BACKEND", "login"),
    ("SBX-AUTH-LOGIN-FRONTEND", "login"),
    ("DEMO-NOTES-EDIT-BACKEND", "notes-edit"),
    ("DEMO-NOTES-EDIT-FRONTEND", "notes-edit"),
    ("SCOPE-API-V2-BACKEND", "api-v2"),
    ("SCOPE-API-V2-FRONTEND", "api-v2"),
    ("SCOPE-2026-NOTE-V3-BACKEND", "2026-note-v3"),
    ("SCOPE-2026-NOTE-V3-FRONTEND", "2026-note-v3"),
    ("Customer-Profile-V2-BACKEND", "customer-profile-v2"),
    ("Customer-Profile-V2-FRONTEND", "customer-profile-v2"),
    ("Customer-Profile-V2", "customer-profile-v2"),
])
def test_scope_derived_module(scope, expected):
    assert atomize._slug(scope, atomize._rules()) == expected


def test_backend_and_frontend_share_function_name(tmp_path):
    rules = atomize._rules()
    for base, name, package_token, java_class in [
        ("SBX-AUTH-LOGIN", "login", "login", "LoginController"),
        ("DEMO-NOTES-EDIT", "notes-edit", "notesedit", "NotesEditController"),
        ("SCOPE-API-V2", "api-v2", "apiv2", "ApiV2Controller"),
        ("SCOPE-2026-NOTE-V3", "2026-note-v3", "m2026notev3", "M2026NoteV3Controller"),
    ]:
        be = atomize._slug(base + "-BACKEND", rules)
        fe = atomize._slug(base + "-FRONTEND", rules)
        assert be == fe == name
        backend_paths = atomize._route("BACKEND", be, rules, tmp_path)
        frontend_paths = atomize._route("FRONTEND", fe, rules, tmp_path)
        assert backend_paths[0].endswith(f"/time/{package_token}/{java_class}.java")
        assert frontend_paths[0] == f"frontend/src/app/{name}/page.tsx"
        for path in backend_paths:
            java_package = path.split("/src/main/java/")[1].rsplit("/", 1)[0]
            tokens = java_package.split("/")
            assert all(re.fullmatch(r"[a-z][a-z0-9]*", token) for token in tokens)
            assert "-" not in java_package
            assert re.fullmatch(r"[A-Z][A-Za-z0-9]*\.java", path.rsplit("/", 1)[1])
        for path in frontend_paths:
            assert re.fullmatch(r"frontend/src/(?:app|lib)/[a-z0-9][a-z0-9/-]*\.(?:tsx|ts)", path)


def test_java_package_keyword_fails_closed(tmp_path):
    rules = atomize._rules()
    with pytest.raises(atomize.AtomBlocked, match="ATOM_JAVA_PACKAGE_INVALID"):
        atomize._route("BACKEND", "class", rules, tmp_path)


def test_invalid_area_suffix_is_not_silently_removed():
    rules = atomize._rules()
    assert atomize._slug("WORK-LOGIN-PLATFORM", rules) == "work-login-platform"


def test_reject_empty_function_after_namespace(tmp_path):
    rules = atomize._rules()
    with pytest.raises(atomize.AtomBlocked, match="ATOM_IDENTITY_INVALID"):
        atomize._slug("-BACKEND", rules)
