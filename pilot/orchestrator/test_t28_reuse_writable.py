"""T28: a file the task is authorized to extend is not a duplicate of itself."""
from __future__ import annotations

import difflib
import hashlib
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from pilot.worker_v08.reuse_guard import check, DuplicateComponent  # noqa: E402

CTRL = "apps/time-service/src/main/java/demo/GadgetController.java"
TEST = "apps/time-service/src/test/java/demo/GadgetControllerTest.java"
BODY = ('public class GadgetController {\n'
        '@GetMapping("/api/gadgets")\n'
        'public String list(String q) { return q; }\n}\n')


def entry(tmp_path, rel=CTRL, value=BODY):
    path = tmp_path / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(value)
    return {"path": rel, "sha256": hashlib.sha256(value.encode()).hexdigest()}


def test_extending_a_writable_file_in_place_passes(tmp_path):
    ctx = [entry(tmp_path)]
    updated = BODY.replace("list(String q)", "list(String auth, String q)")
    patch = f"diff --git a/{CTRL} b/{CTRL}\n" + "".join(
        difflib.unified_diff(BODY.splitlines(True), updated.splitlines(True),
                             fromfile=f"a/{CTRL}", tofile=f"b/{CTRL}"))
    patch += f"diff --git a/{TEST} b/{TEST}\n--- /dev/null\n+++ b/{TEST}\n@@ -0,0 +1 @@\n+// login first\n"
    check(tmp_path, patch, ctx, writable=[CTRL, TEST])


def test_same_edit_without_authorization_is_still_rejected(tmp_path):
    ctx = [entry(tmp_path)]
    patch = f"diff --git a/{CTRL} b/{CTRL}\n+// change\n"
    with pytest.raises(DuplicateComponent, match="reuse_context"):
        check(tmp_path, patch, ctx)


def test_copying_the_writable_endpoint_elsewhere_is_still_rejected(tmp_path):
    ctx = [entry(tmp_path)]
    other = "apps/time-service/src/main/java/demo/CopyController.java"
    patch = f'diff --git a/{other} b/{other}\n+@GetMapping("/api/gadgets")\n'
    with pytest.raises(DuplicateComponent, match="endpoint"):
        check(tmp_path, patch, ctx, writable=[CTRL])


def test_native_run_passes_the_registered_write_scope():
    source = (ROOT / "pilot/worker_v08/native_run.py").read_text("utf-8")
    assert 'writable=raw_task.get("write_path_patterns", [])' in source
