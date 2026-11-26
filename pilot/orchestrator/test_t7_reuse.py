"""T7 offline catalogue and reuse guards; no fixture or hidden exam modifications."""
import hashlib
import json
import difflib
from pathlib import Path
import sys

import pytest

from analysis.host.request_catalog import resolve, CatalogueBlocked
from pilot.orchestrator.reuse_assessment import index, assess, ReuseBlocked
from pilot.worker_v08.reuse_guard import check, DuplicateComponent


def catalogue(tmp_path):
    base = tmp_path / "analysis/fixtures"
    for dirname, code in (("screen_one", "SCREEN-ONE"), ("screen_two", "SCREEN-TWO")):
        target = base / dirname
        target.mkdir(parents=True)
        (target / "SOURCE_PIN.json").write_text(json.dumps({"fixture_id": code}))


def test_catalogue_exact_screen_resolution(tmp_path):
    catalogue(tmp_path)
    assert resolve(tmp_path, b"Implement SCREEN-ONE")[0] == "SCREEN-ONE"
    with pytest.raises(CatalogueBlocked, match="PEDIDO_AMBIGUO"):
        resolve(tmp_path, b"Implement SCREEN-ONE and SCREEN-TWO")
    with pytest.raises(CatalogueBlocked, match="PEDIDO_AMBIGUO"):
        resolve(tmp_path, b"Build a screen without code")
    with pytest.raises(CatalogueBlocked, match="PANTALLA_NO_EN_CATALOGO"):
        resolve(tmp_path, b"Build SCREEN-ABSENT")


def source(tmp_path, rel, value):
    path = tmp_path / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(value)
    return {"path": rel, "sha256": hashlib.sha256(value.encode()).hexdigest()}


def new_file_patch(path, content):
    return f"diff --git a/{path} b/{path}\n" + "".join(
        difflib.unified_diff([], content.splitlines(True), fromfile="/dev/null", tofile=f"b/{path}"))


def complete_fixture_patch(patch):
    # Older synthetic fixtures specified added lines only; construct a real hunk.
    path = patch.splitlines()[0].split(" b/")[1]
    return new_file_patch(path, "".join(line[1:] + "\n" for line in patch.splitlines()[1:]))



def test_index_exact_evidence_and_indeterminate_without_explicit_rule(tmp_path):
    source(tmp_path, "apps/time-service/src/main/java/demo/Service.java",
           'public class Worker {\n'
           '@PostMapping("/api/example")\n'
           'public String process(String input) { return "ok"; }\n'
           '// REQ-EXAMPLE\n}\n')
    catalogue = index(tmp_path)
    keys = {(x["kind"], x["key"]) for x in catalogue["entries"]}
    assert ("endpoint", "POST /api/example") in keys
    assert ("public_signature", "type:Worker") in keys
    assert ("implemented_rule", "REQ-EXAMPLE") in keys
    report = assess(catalogue, [{"requirement_id": "REQ-EXAMPLE",
                                 "source_requirement_id": "RULE-EXAMPLE"}])
    assert report["obligations"][0]["decision"] == "REUSE_AS_IS"
    with pytest.raises(ReuseBlocked, match="REUTILIZACION_INDETERMINADA"):
        assess(catalogue, [{"requirement_id": "REQ-UNKNOWN",
                            "source_requirement_id": "RULE-UNKNOWN"}])


def test_duplicate_endpoint_rejected(tmp_path):
    source(tmp_path, "apps/time-service/src/main/java/demo/Old.java",
           '@PostMapping("/api/example")\npublic class Old {}\n')
    patch = ('diff --git a/apps/time-service/src/main/java/demo/New.java '
             'b/apps/time-service/src/main/java/demo/New.java\n'
             '+@PostMapping("/api/example")\n')
    with pytest.raises(DuplicateComponent, match="DUPLICA_COMPONENTE_EXISTENTE:endpoint"):
        check(tmp_path, complete_fixture_patch(patch), [])


def test_copy_service_with_renamed_class_same_public_signature_rejected(tmp_path):
    entry = source(tmp_path, "apps/time-service/src/main/java/demo/Existing.java",
                   'public class Existing {\n'
                   'public String check(String input) { return input; }\n}\n')
    patch = ('diff --git a/apps/time-service/src/main/java/demo/New.java '
             'b/apps/time-service/src/main/java/demo/New.java\n'
             '+public class New {\n'
             '+public String changed(String input) { return input; }\n')
    with pytest.raises(DuplicateComponent, match="DUPLICA_COMPONENTE_EXISTENTE:signature"):
        check(tmp_path, complete_fixture_patch(patch), [entry])


def test_modify_reuse_context_rejected(tmp_path):
    entry = source(tmp_path, "apps/time-service/src/main/java/demo/Existing.java",
                   "public class Existing {}")
    path = entry["path"]
    patch = f"diff --git a/{path} b/{path}\n+// modification\n"
    with pytest.raises(DuplicateComponent, match="DUPLICA_COMPONENTE_EXISTENTE:reuse_context"):
        check(tmp_path, patch, [entry])


def test_use_existing_service_without_modifying_or_copying_passes(tmp_path):
    entry = source(tmp_path, "apps/time-service/src/main/java/demo/Existing.java",
                   'public class Existing {\n'
                   'public String check(String input) { return input; }\n}\n')
    patch = ('diff --git a/apps/time-service/src/main/java/demo/New.java '
             'b/apps/time-service/src/main/java/demo/New.java\n'
             '+public class New {\n'
             '+private final Existing existing;\n')
    check(tmp_path, complete_fixture_patch(patch), [entry])


def test_distinct_methods_with_same_shape_are_not_duplicates(tmp_path):
    entry = source(tmp_path, "apps/time-service/src/main/java/demo/Existing.java",
                   'public class Existing {\n'
                   'public String read(String input) { return load(input); }\n}\n')
    path = "apps/time-service/src/main/java/demo/New.java"
    patch = (f"diff --git a/{path} b/{path}\n"
             '+public String remove(String input) { return delete(input); }\n')
    check(tmp_path, complete_fixture_patch(patch), [entry])


def test_record_components_are_not_method_signatures(tmp_path):
    entry = source(tmp_path, "apps/time-service/src/main/java/demo/Existing.java",
                   'public record Existing(String first, String second) { public Existing { validate(first); } }\n')
    path = "apps/time-service/src/main/java/demo/New.java"
    patch = (f"diff --git a/{path} b/{path}\n"
             '+public record New(String status, String token) { public New { validate(status); } }\n')
    check(tmp_path, complete_fixture_patch(patch), [entry])


def test_same_method_name_different_behavior_is_not_duplicate(tmp_path):
    entry = source(tmp_path, "apps/time-service/src/main/java/demo/Existing.java",
                   'public String lookup(String key) { return cache.get(key); }\n')
    path = "apps/time-service/src/main/java/demo/New.java"
    patch = (f"diff --git a/{path} b/{path}\n"
             '+public String lookup(String key) { return store.find(key); }\n')
    check(tmp_path, complete_fixture_patch(patch), [entry])


def test_copied_body_with_comments_and_nested_braces_rejected(tmp_path):
    entry = source(tmp_path, "apps/time-service/src/main/java/demo/Existing.java",
                   'public String read(String key) { if (key == null) { return "}"; } return key; }\n')
    path = "apps/time-service/src/main/java/demo/New.java"
    patch = (f"diff --git a/{path} b/{path}\n"
             '+public String renamed(String key) {\n'
             '+  // comment\n'
             '+  if (key == null) { return "}"; }\n'
             '+  return key;\n'
             '+}\n')
    with pytest.raises(DuplicateComponent, match=r"Existing.java#read:.*New.java#renamed"):
        check(tmp_path, complete_fixture_patch(patch), [entry])


def test_complete_postimage_detects_copy_across_diff_hunks(tmp_path):
    import difflib

    entry = source(tmp_path, "apps/time-service/src/main/java/demo/Existing.java",
                   'public String read(String key) {\n'
                   '    return store.find(key);\n}\n')
    path = "apps/time-service/src/main/java/demo/New.java"
    old = ('public String previous(String key) {\n'
           '    return cache.get(key);\n}\n')
    new = ('public String renamed(String key) {\n'
           '    return store.find(key);\n}\n')
    source(tmp_path, path, old)
    patch = f"diff --git a/{path} b/{path}\n" + "".join(
        difflib.unified_diff(old.splitlines(True), new.splitlines(True),
                             fromfile=f"a/{path}", tofile=f"b/{path}", n=0))
    with pytest.raises(DuplicateComponent, match="DUPLICA_COMPONENTE_EXISTENTE:signature"):
        check(tmp_path, patch, [entry])


def test_unchanged_legacy_duplicate_is_not_attributed_to_new_patch(tmp_path):
    import difflib

    old = 'public String read(String key) { return key; }\n'
    entry = source(tmp_path, "apps/time-service/src/main/java/demo/Existing.java", old)
    path = "apps/time-service/src/main/java/demo/New.java"
    source(tmp_path, path, old)
    new = old + 'public String remove(String key) { return delete(key); }\n'
    patch = f"diff --git a/{path} b/{path}\n" + "".join(
        difflib.unified_diff(old.splitlines(True), new.splitlines(True),
                             fromfile=f"a/{path}", tofile=f"b/{path}"))
    check(tmp_path, patch, [entry])


def test_invalid_hunk_is_fail_closed(tmp_path):
    entry = source(tmp_path, "apps/time-service/src/main/java/demo/Existing.java",
                   'public String read(String key) { return key; }\n')
    path = "apps/time-service/src/main/java/demo/New.java"
    patch = (f"diff --git a/{path} b/{path}\n"
             '@@ -0,0 +1,2 @@\n'
             '+public String renamed(String key) { return key; }\n')
    with pytest.raises(DuplicateComponent, match="REUTILIZACION_INDETERMINADA"):
        check(tmp_path, patch, [entry])



def test_duplicate_type_still_rejected(tmp_path):
    source(tmp_path, "apps/time-service/src/main/java/demo/Existing.java",
           'public record Existing(String value) {}\n')
    path = "apps/time-service/src/main/java/demo/New.java"
    patch = (f"diff --git a/{path} b/{path}\n"
             '+public record Existing(String value) {}\n')
    with pytest.raises(DuplicateComponent, match="DUPLICA_COMPONENTE_EXISTENTE:type"):
        check(tmp_path, complete_fixture_patch(patch), [])


@pytest.mark.parametrize("header", [
    'public String renamed(@RequestHeader(name = "A") String input)',
    'public String renamed(@RequestBody String input)',
    'public String renamed(String input) throws IOException, SQLException',
    'public String renamed(final String input)',
])
def test_annotated_and_throws_copy_rejected(tmp_path, header):
    entry = source(tmp_path, "apps/time-service/src/main/java/demo/Existing.java",
                   'public String original(@RequestHeader(name = "A") String input) { return store.find(input); }\n')
    path = "apps/time-service/src/main/java/demo/New.java"
    with pytest.raises(DuplicateComponent, match="DUPLICA_COMPONENTE_EXISTENTE:signature"):
        check(tmp_path, new_file_patch(path, header + " { return store.find(input); }\n"), [entry])


@pytest.mark.parametrize("replacement", [
    'public String renamed(String auth) { String stored = store.find(auth); return stored; }',
    'public String renamed(String input) { String value = store.find(input); return value; }',
    'public String renamed(String input) { final String stored = store.find(input); return stored; }',
    'public String renamed(String input) { String stored = store.find(input); ; return stored; }',
])
def test_trivial_copy_variants_rejected(tmp_path, replacement):
    entry = source(tmp_path, "apps/time-service/src/main/java/demo/Existing.java",
                   'public String original(String input) { String stored = store.find(input); return stored; }\n')
    path = "apps/time-service/src/main/java/demo/New.java"
    with pytest.raises(DuplicateComponent, match="DUPLICA_COMPONENTE_EXISTENTE:signature"):
        check(tmp_path, new_file_patch(path, replacement + "\n"), [entry])


def test_nested_generic_parameters_and_annotation_arrays(tmp_path):
    entry = source(tmp_path, "apps/time-service/src/main/java/demo/Existing.java",
                   'public Map<String, List<Integer>> original(@A(values = {"x", "y"}) '
                   'Map<String, List<Integer>> data, String key) throws IOException { return store.get(data, key); }\n')
    path = "apps/time-service/src/main/java/demo/New.java"
    copied = ('public Map<String,List<Integer>> renamed(Map<String,List<Integer>> values, final String name) '
              '{ return store.get(values, name); }\n')
    with pytest.raises(DuplicateComponent, match="DUPLICA_COMPONENTE_EXISTENTE:signature"):
        check(tmp_path, new_file_patch(path, copied), [entry])


@pytest.mark.parametrize("replacement", [
    'public String read(String key) { return store.remove(key); }',
    'public String read(String key) { return store.find("other"); }',
    'public String read(String key) { return this.key; }',
])
def test_normalization_preserves_calls_literals_and_members(tmp_path, replacement):
    entry = source(tmp_path, "apps/time-service/src/main/java/demo/Existing.java",
                   'public String read(String key) { return store.find(key); }\n')
    path = "apps/time-service/src/main/java/demo/New.java"
    check(tmp_path, new_file_patch(path, replacement + "\n"), [entry])


def test_fragment_without_hunk_is_rejected(tmp_path):
    path = "apps/time-service/src/main/java/demo/New.java"
    with pytest.raises(DuplicateComponent, match="REUTILIZACION_INDETERMINADA"):
        check(tmp_path, f"diff --git a/{path} b/{path}\n+public class New {{}}\n", [])
