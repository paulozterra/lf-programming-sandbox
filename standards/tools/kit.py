"""Kit base: valida digests y renderiza placeholders seguros."""
import argparse
import hashlib
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
KIT = ROOT / "standards/kit-base"
MANIFEST = KIT / "kit.json"
SCHEMA = re.compile(r"[a-z][a-z0-9_]*\Z")
PREFIX = re.compile(r"[A-Z]{2,6}\Z")
UNRESOLVED = re.compile(r"\$\{[^}]+\}")


def verify():
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    failures = []
    for entry in manifest["files"]:
        path = KIT / entry["path"]
        if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != entry["sha256"]:
            failures.append("DIGEST_MISMATCH " + entry["path"])
    return failures


def render(schema, trace_prefix, output):
    if not SCHEMA.fullmatch(schema) or not PREFIX.fullmatch(trace_prefix):
        raise ValueError("INVALID_PLACEHOLDER")
    if verify():
        raise ValueError("DIGEST_MISMATCH")
    output.mkdir(parents=True, exist_ok=True)
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    for entry in manifest["files"]:
        original = (KIT / entry["path"]).read_text(encoding="utf-8")
        content = original.replace("${schema}", schema).replace("${trace_prefix}", trace_prefix)
        if UNRESOLVED.search(content):
            raise ValueError("UNRESOLVED_PLACEHOLDER " + entry["path"])
        (output / Path(entry["path"]).name).write_text(content, encoding="utf-8")


def main(argv=None):
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest="action", required=True)
    sub.add_parser("verify")
    r = sub.add_parser("render")
    r.add_argument("--schema", required=True)
    r.add_argument("--trace-prefix", required=True)
    r.add_argument("--out", required=True, type=Path)
    a = p.parse_args(argv)
    if a.action == "verify":
        failures = verify()
        for issue in failures:
            print(issue)
        return int(bool(failures))
    try:
        render(a.schema, a.trace_prefix, a.out)
    except ValueError as err:
        print("ERROR", err)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
