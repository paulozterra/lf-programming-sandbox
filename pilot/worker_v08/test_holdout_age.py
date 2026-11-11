"""Offline CP2.1: no actual private key, oracle or network."""
from __future__ import annotations
import copy
import hashlib
import io
import json
import subprocess
from contextlib import redirect_stdout, redirect_stderr
from pathlib import Path
from unittest.mock import patch

import pytest
from holdout_age import (AgeBlocked, checked_ciphertext, decrypt_private,
                         holdout_ref, validate_recipient)
from native_run import load_registration, registration_holdout_ref
from register_task_context import native_registration_bytes, write_native_registration

HERE = Path(__file__).resolve().parents[2]
REF = "pilot/holdouts/example.oracle.json.age"
FAKE_KEY_MARKER = "AGE-SECRET-KEY-1NOT-A-REAL-KEY"


def test_public_recipient_format_and_placeholder():
    # Syntactically valid fixture, not a keypair.
    syntactic = "age1" + "q" * 58
    assert validate_recipient("# public recipient\n" + syntactic + "\n") == syntactic
    for invalid in ("", "placeholder", "AGE-SECRET-KEY-1FAKE", "age1short",
                    syntactic + "\n" + syntactic):
        with pytest.raises(AgeBlocked, match="HOLDOUT_RECIPIENT_INVALID"):
            validate_recipient(invalid)
    sample = (HERE / "pilot/holdouts/recipient.txt.example").read_text("utf-8")
    assert "AGE-SECRET-KEY-" not in sample


@pytest.mark.parametrize("bad", [
    "../pilot/holdouts/example.oracle.json.age",
    "pilot/holdouts/../example.oracle.json.age",
    "pilot/holdouts/other.oracle.json.age",
    "vendor/example.oracle.json.age",
    "/tmp/example.oracle.json.age",
    "pilot/holdouts/example.oracle.json.age/../x",
])
def test_ref_escape_blocked(bad):
    with pytest.raises(AgeBlocked, match="HOLDOUT_REF_INVALID"):
        holdout_ref("example", bad)


def test_symlink_and_missing_ciphertext_block(tmp_path):
    encrypted = tmp_path / REF
    encrypted.parent.mkdir(parents=True)
    with pytest.raises(AgeBlocked, match="HOLDOUT_CIPHERTEXT_MISSING"):
        checked_ciphertext(tmp_path, "example", REF)
    dest = tmp_path / "other.age"
    dest.write_bytes(b"not-an-oracle")
    encrypted.symlink_to(dest)
    with pytest.raises(AgeBlocked, match="HOLDOUT_REF_INVALID"):
        checked_ciphertext(tmp_path, "example", REF)


def test_broken_ciphertext_and_sha_drift_are_private(tmp_path):
    encrypted = tmp_path / REF
    encrypted.parent.mkdir(parents=True)
    encrypted.write_bytes(b"tampered-ciphertext-only")
    private = tmp_path / "private"
    stdout, stderr = io.StringIO(), io.StringIO()
    def decrypt_failure(*args, **kwargs):
        return subprocess.CompletedProcess(args[0], 1, b"", b"opaque failure with secret")
    with patch("holdout_age.subprocess.run", side_effect=decrypt_failure):
        with redirect_stdout(stdout), redirect_stderr(stderr):
            with pytest.raises(AgeBlocked, match="HOLDOUT_DECRYPT_FAILED"):
                decrypt_private(tmp_path, "example", REF, "a" * 64,
                                FAKE_KEY_MARKER, private)
    assert not (private / ".age-identity").exists()
    assert not (private / "holdout.oracle.json").exists()
    assert "tampered-ciphertext-only" not in stdout.getvalue() + stderr.getvalue()
    assert FAKE_KEY_MARKER not in stdout.getvalue() + stderr.getvalue()
    assert "opaque failure" not in stdout.getvalue() + stderr.getvalue()

    # Fake deterministic executable output ONLY, never real decryption or identity.
    content = b"synthetic-offline-oracle-not-secret"
    def decrypted(*args, **kwargs):
        output = Path(args[0][args[0].index("--output") + 1])
        output.write_bytes(content)
        return subprocess.CompletedProcess(args[0], 0, b"", b"")
    with patch("holdout_age.subprocess.run", side_effect=decrypted):
        with pytest.raises(AgeBlocked, match="NATIVE_HOLDOUT_SHA_DRIFT"):
            decrypt_private(tmp_path, "example", REF, "b" * 64,
                            FAKE_KEY_MARKER, private)
    assert not (private / ".age-identity").exists()
    assert not (private / "holdout.oracle.json").exists()
    with patch("holdout_age.subprocess.run", side_effect=decrypted):
        output = decrypt_private(tmp_path, "example", REF,
                                 hashlib.sha256(content).hexdigest(),
                                 FAKE_KEY_MARKER, private)
    assert output.read_bytes() == content
    assert not (private / ".age-identity").exists()


def test_new_optional_ref_and_unmodified_legacy_registration(tmp_path):
    template = json.loads((HERE / "pilot/worker_v08/native_tasks/ex8.json").read_text("utf-8"))
    spec = copy.deepcopy(template["task_spec"])
    legacy = native_registration_bytes(spec, "a" * 64)
    assert set(json.loads(legacy)) == {"task_spec", "holdout_sha256"}
    # Existing ex6/ex7/ex8 remain exactly two-key registrations.
    for task in ("ex6", "ex7", "ex8"):
        record = json.loads((HERE / "pilot/worker_v08/native_tasks" / (task + ".json")).read_text("utf-8"))
        assert set(record) == {"task_spec", "holdout_sha256"}
        result, sha = load_registration(HERE, task)
        assert result == record["task_spec"] and sha == record["holdout_sha256"]
        assert registration_holdout_ref(HERE, task) is None
    out = tmp_path / "pilot/worker_v08/native_tasks/sample.json"
    write_native_registration(tmp_path, "sample", out, spec, "a" * 64,
                              "pilot/holdouts/sample.oracle.json.age")
    loaded, sha = load_registration(tmp_path, "sample")
    assert loaded == spec and sha == "a" * 64
    assert registration_holdout_ref(tmp_path, "sample") == "pilot/holdouts/sample.oracle.json.age"


def test_trigger_never_receives_age_secret_or_oracle_and_workflow_private_only():
    trigger = (HERE / ".github/workflows/worker-native-trigger.yml").read_text("utf-8")
    trusted = (HERE / ".github/workflows/worker-native.yml").read_text("utf-8")
    assert "PILOT_HOLDOUT_AGE_KEY" not in trigger
    assert "secrets." not in trigger
    assert "holdout.oracle.json" not in trigger
    assert "PILOT_HOLDOUT_AGE_KEY:" in trusted
    assert "secrets.PILOT_HOLDOUT_AGE_KEY" in trusted
    assert "AGE_TARBALL_SHA_DRIFT" in trusted
    assert "cbe24006683f8eb669266162894b9a522a1af52f2665fbc63a4bb032ed26ac10" in trusted
    assert 'if [ -n "$HOLDOUT_REF" ]; then' in trusted
    assert 'PILOT_HOLDOUT_B64' in trusted
    assert "set -x" not in trusted
