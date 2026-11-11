"""EX6 source-only real-evidence loader. Does not call models or mutate producers.

Reads the *original* GitHub Actions artifact ZIP bytes pinned below, not rebuilt
copies or hand-crafted success fixtures. A PASS here authenticates only ZIP
identity + internally consistent public statements, never production authority.
PG-04..PG-14 have NOT been executed merely by loading the evidence.
"""
from __future__ import annotations

import hashlib
import io
import json
import re
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / "evidence"
RUN_ID = 42674262914
BASE_SHA = "53ab6b1a85da95f3e2a38d7f3298af731c6698ab"
PROPOSAL_COMMIT_SHA = "13ef9c319fb62f7e08f6f030d447c60ee7bfa7f5"
TASK_PACK_SHA256 = "31a01a43c13d1a6c8ef5d861825e03211d05566abecded7eeea023dcfaba048e"
PROPOSAL_SHA256 = "c469a00ebb78d1346cecab0b19bd7c385e13e428a2eaf1fccea61e30dc838d78"
RUN_REF = "https://github.com/paulozterra/lf-programming-sandbox/actions/runs/42674262914"
REPO = "paulozterra/lf-programming-sandbox"

# Bytes pinned against the original GitHub Actions ZIP downloads and their contents.
ARCHIVES = {
    "native-attempt-proof.zip": (
        "237baba0c483f1330244dff94314fc883a7321b1f41295686dc501b4f7527114",
        {"attempt-proof.json": "e45dd320598739b959849137033e6908fa6a12cfbdb0faacdce1a009f6120336"},
    ),
    "native-visible-feedback-and-cost.zip": (
        "fb76b00b8870ebc0f11b509e5770a185f58e2564b4af8e9fb9349a74e9625e5b",
        {
            "feedback.json": "9b796e549eccc582ee0717d4bcf4a6859237c49eca6699fe403d9075595e66bb",
            "cost.json": "78d6445696d10a2b1bb15f1bc936cd05c3882bd64bd5327757d1b7ff0cbffe25",
            "status.json": "c2725691a6f941648becd262ff45a51b3bcb1a883ac0fd81b274019edc0cb6af",
        },
    ),
    "native-verified-patch.zip": (
        "57f73f828ec5a926b6f77e712ed952e2a7c79a1471e16f73f6810cb88ec4dd04",
        {"worker.patch": "e0c3675f7bc7b2b80ed199be3cd5fffadae564d8b354da75ef6c56bb21bf7ce5"},
    ),
}

J = "apps/time-service/src/main/java/lf/sandbox/time/reminder/"
EXACT_PATHS = sorted(J + n for n in (
    "ReminderStats.java", "ReminderStatsService.java", "ReminderStatsController.java"
))


class EX6EvidenceBlocked(ValueError):
    pass


def fail(reason: str):
    raise EX6EvidenceBlocked(reason)


def sha(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")


def read_bundle(root: Path = EVIDENCE) -> dict[str, bytes]:
    files = {}
    for name, (zip_sha, entries) in ARCHIVES.items():
        path = root / name
        if not path.is_file() or path.is_symlink():
            fail("EX6_ZIP_MISSING_OR_SYMLINK:" + name)
        raw = path.read_bytes()
        if sha(raw) != zip_sha:
            fail("EX6_ZIP_SHA256_DRIFT:" + name)
        try:
            with zipfile.ZipFile(io.BytesIO(raw)) as z:
                if sorted(z.namelist()) != sorted(entries):
                    fail("EX6_ZIP_MEMBER_UNIVERSE_DRIFT:" + name)
                for member, member_sha in entries.items():
                    data = z.read(member)
                    if sha(data) != member_sha:
                        fail("EX6_MEMBER_SHA256_DRIFT:" + member)
                    if member in files:
                        fail("EX6_DUPLICATE_MEMBER")
                    files[member] = data
        except (zipfile.BadZipFile, RuntimeError, KeyError) as exc:
            fail("EX6_ZIP_INVALID:" + type(exc).__name__)
    return files


def load_evidence(root: Path = EVIDENCE) -> dict:
    files = read_bundle(root)
    try:
        values = {k: json.loads(files[k]) for k in (
            "attempt-proof.json", "feedback.json", "cost.json", "status.json"
        )}
    except (UnicodeError, ValueError) as exc:
        fail("EX6_PUBLIC_JSON_INVALID:" + type(exc).__name__)
    proof, feedback, cost, status = (
        values["attempt-proof.json"], values["feedback.json"],
        values["cost.json"], values["status.json"]
    )
    if proof != {
        "attempt": 1, "run_id": RUN_ID, "task_id": "ex6",
        "task_pack_sha256": TASK_PACK_SHA256,
    }:
        fail("EX6_ATTEMPT_PROOF_DRIFT")
    if (status.get("attempt") != 1 or status.get("task_id") != "ex6"
        or status.get("status") != "PASS"
        or status.get("task_pack_sha256") != TASK_PACK_SHA256
        or status.get("proposal_sha256") != PROPOSAL_SHA256
        or status.get("production_authority") is not False
        or status.get("receipt_authenticated") is not False
        or status.get("authority") != "REAL_SANDBOX_UNAUTHENTICATED"):
        fail("EX6_STATUS_OR_AUTHORITY_DRIFT")
    if status.get("feedback_sha256") != sha(canonical(feedback)):
        fail("EX6_FEEDBACK_DIGEST_DRIFT")
    if (cost.get("real_api_usage") is not False or cost.get("api_calls") != 0
        or cost.get("total_usd") != 0 or cost.get("cost_scope") != "incremental_api"
        or cost.get("subscription_cost") != "NOT_EVALUATED"):
        fail("EX6_COST_SCOPE_OR_ZERO_API_DRIFT")
    if (feedback.get("kind") != "VISIBLE_ACCEPTANCE_ONLY"
        or feedback.get("attempt") != 1 or
        sorted(x.get("name") for x in feedback.get("commands", [])) !=
        ["ex6-visible-check", "time-service-package"] or
        any(x.get("status") != "PASS" or x.get("returncode") != 0
            for x in feedback["commands"])):
        fail("EX6_VISIBLE_ACCEPTANCE_DRIFT")
    patch = files["worker.patch"].decode("utf-8")
    paths = re.findall(r"(?m)^diff --git a/(\S+) b/(\S+)$", patch)
    if (not paths or sorted(a for a, z in paths) != EXACT_PATHS
        or any(a != z for a, z in paths)
        or patch.count("--- /dev/null") != 3
        or patch.count("new file mode 100644") != 3):
        fail("EX6_PATCH_PATH_SCOPE_DRIFT")
    return {
        "run_ref": RUN_REF, "task_id": "ex6", "source_base_sha": BASE_SHA,
        "proposal_commit_sha": PROPOSAL_COMMIT_SHA,
        "task_pack_sha256": TASK_PACK_SHA256,
        "proposal_sha256": PROPOSAL_SHA256,
        "patch_sha256": sha(files["worker.patch"]),
        "changed_paths": EXACT_PATHS,
        "status_reported": "PASS",
        "visible_acceptance_reported": "PASS",
        "api_calls_reported": 0,
        "incremental_api_cost_reported": "0",
        "subscription_cost": "NOT_EVALUATED",
        "receipt_authenticated": False,
        "production_authority": False,
        "handoff_allowed": False,
    }


def stage_matrix() -> list[dict]:
    """No false PASS: stage constructors require separate genuine EX6 inputs."""
    return [{
        "stage": f"PG-{number:02d}",
        "before": "NOT_RUN",
        "after": "NOT_RUN",
        "reason": "EX6_REAL_STAGE_PRODUCER_NOT_YET_INVOKED",
    } for number in range(4, 15)]


if __name__ == "__main__":
    print(json.dumps({"evidence": load_evidence(), "stages": stage_matrix()},
                     sort_keys=True, indent=2))
