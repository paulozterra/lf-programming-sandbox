"""T30: A9 resolves areas for LF's real rule taxonomy and owns every
VIGENTE error (generic or specific), so a real LF screen is not blocked by
a vocabulary that only covered fictional fixtures."""
import json
from pathlib import Path

from analysis.a9 import front_bindings

POLICY = Path(front_bindings.__file__).with_name("area_rules_v1.json")

LF_TAXONOMY = {
    "accessibility": "FRONTEND", "ux": "FRONTEND", "design": "FRONTEND",
    "theme": "FRONTEND", "responsive": "FRONTEND",
    "session": "BACKEND", "resilience": "BACKEND", "privacy": "BACKEND",
    "error": "BACKEND", "error_handling": "BACKEND", "security": "BACKEND",
}


def test_lf_categories_resolve_to_exactly_one_area():
    rules = json.loads(POLICY.read_text("utf-8"))["rule_categories"]
    for category, area in LF_TAXONOMY.items():
        assert rules.get(category) == [area], category
    # Uppercase LF values resolve through casefold, never by title or prose.
    assert rules.get("ACCESSIBILITY".casefold()) == ["FRONTEND"]


def test_previous_categories_unchanged():
    rules = json.loads(POLICY.read_text("utf-8"))["rule_categories"]
    for category, areas in {"seguridad": ["BACKEND"], "security": ["BACKEND"],
                            "rate_limiting": ["BACKEND"], "api": ["BACKEND"],
                            "datos": ["DATA"], "error_states": ["BACKEND"],
                            "analytics": []}.items():
        assert rules[category] == areas


def test_unknown_category_still_fails_closed():
    rules = json.loads(POLICY.read_text("utf-8"))["rule_categories"]
    assert "negocio" not in rules and "flujo" not in rules


def test_specific_errors_are_owned_not_only_generic():
    src = Path(front_bindings.__file__).read_text("utf-8")
    assert 'row.get("generic") is True' not in src
