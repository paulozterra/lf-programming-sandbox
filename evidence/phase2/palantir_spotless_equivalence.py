#!/usr/bin/env python3
"""CHG-0029: exact Palantir Spotless formatting and full javac -g:none equivalence.

--emit: build formatter output in an isolated tree, print BASE64 per changed Java.
--check: require actual Java bytes already equal to Spotless output.
Never write to checkout, vendor, holdout, Supabase or historical AOSP evidence.
"""
from __future__ import annotations
import argparse
import base64
import hashlib
import json
import pathlib
import shutil
import subprocess
import tempfile

BASE = "f18b2d96b7e1a8263749d35a7afcc9c043521cb8"
SRC = pathlib.Path("apps/time-service/src/main/java")
POM = pathlib.Path("apps/time-service/pom.xml")
CATALOG = pathlib.Path("standards/catalog.json")
EXPECTED_PLUGIN = "3.10.4"
EXPECTED_FORMATTER = "2.102.0"

def run(argv, cwd, timeout=480):
    result = subprocess.run(argv, cwd=cwd, capture_output=True, text=True, timeout=timeout)
    if result.returncode:
        raise RuntimeError("PALANTIR_COMMAND_FAILED:"+str(argv)+":"
                           +result.stderr[-1600:]+result.stdout[-700:])
    return result.stdout.strip()

def require(condition, code):
    if not condition:
        raise RuntimeError("PALANTIR_CLASS_EQ_BLOCK:"+code)

def sha(raw):
    return hashlib.sha256(raw).hexdigest()

def compile_all(root, out, cp):
    paths = sorted((root/SRC).rglob("*.java"))
    require(bool(paths), "JAVA_SOURCES_MISSING")
    out.mkdir(parents=True, exist_ok=False)
    run(["javac", "--release", "21", "-g:none", "-encoding", "UTF-8",
         "-classpath", cp, "-d", str(out), *map(str, paths)], root)
    hashes = {p.relative_to(out).as_posix():sha(p.read_bytes())
              for p in sorted(out.rglob("*.class"))}
    require(bool(hashes), "JAVA_CLASS_OUTPUT_EMPTY")
    return hashes

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", required=True, choices=("emit", "check"))
    args = parser.parse_args()
    root = pathlib.Path(__file__).resolve().parents[2]
    catalog = json.loads((root/CATALOG).read_text(encoding="utf-8"))
    rule = next(x for x in catalog["rules"] if x["id"] == "STD-BE-05")
    tool = rule["enforcement"]["tool"]
    require(EXPECTED_PLUGIN in tool and EXPECTED_FORMATTER in tool,
            "CATALOG_STD_BE_05_VERSION_DRIFT")
    pom = (root/POM).read_text(encoding="utf-8")
    require("<version>"+EXPECTED_PLUGIN+"</version>" in pom
            and "<version>"+EXPECTED_FORMATTER+"</version>" in pom
            and "<palantirJavaFormat>" in pom, "POM_FORMATTER_VERSION_DRIFT")
    paths = [p.relative_to(root) for p in sorted((root/SRC).rglob("*.java"))]
    require(len(paths) >= 10, "SOURCE_INVENTORY_TOO_SMALL")
    with tempfile.TemporaryDirectory(prefix="lf_palantir_2a_") as temp:
        tmp = pathlib.Path(temp)
        old = tmp/"before"
        new = tmp/"after"
        for folder in (old, new):
            target = folder/POM
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(root/POM, target)
            for rel in paths:
                dest = folder/rel
                dest.parent.mkdir(parents=True, exist_ok=True)
                if folder == old:
                    raw = subprocess.run(["git","-C",str(root),"show",BASE+":"+rel.as_posix()],
                                         capture_output=True, check=True).stdout
                else:
                    raw = (root/rel).read_bytes()
                dest.write_bytes(raw)
        cp_path = tmp/"dependencies.txt"
        run(["mvn","-B","-q","-f",str(root/POM),"dependency:build-classpath",
             "-Dmdep.outputFile="+str(cp_path)],root)
        cp = cp_path.read_text(encoding="utf-8").strip()
        require(bool(cp), "MAVEN_CLASSPATH_EMPTY")
        baseline = compile_all(old,tmp/"classes-before",cp)
        run(["mvn","-B","-q","-f",str(new/POM),"spotless:apply"],new)
        run(["mvn","-B","-q","-f",str(new/POM),"spotless:check"],new)
        formatted = compile_all(new,tmp/"classes-after",cp)
        require(baseline == formatted, "CLASS_BYTES_DIFFER")
        changed = [x for x in paths
                   if (old/x).read_bytes() != (new/x).read_bytes()]
        if args.mode == "check":
            require(all((root/x).read_bytes()==(new/x).read_bytes() for x in paths),
                    "CHECKOUT_NOT_PALANTIR_FORMATTED")
        else:
            for rel in changed:
                payload = base64.b64encode((new/rel).read_bytes()).decode("ascii")
                print("LF_PALANTIR_FORMAT_FILE="+rel.as_posix()+":"+payload)
        receipt = {
            "schema_version":"LF_PALANTIR_CLASS_EQ_V1",
            "baseline_commit":BASE,
            "catalog_version":catalog["catalog_version"],
            "standard_rule":"STD-BE-05",
            "spotless_version":EXPECTED_PLUGIN,
            "palantir_java_format_version":EXPECTED_FORMATTER,
            "javac_options":["--release","21","-g:none","-encoding","UTF-8"],
            "java_sources":len(paths),
            "changed_source_paths":[p.as_posix() for p in changed],
            "class_count":len(baseline),
            "class_sha256_before":baseline,
            "class_sha256_after":formatted,
            "class_bytes_identical":True,
            "candidate_only":True,
            "model_calls":0
        }
        print("LF_PALANTIR_CLASS_EQ_RECEIPT="+json.dumps(receipt,sort_keys=True,separators=(",",":")))
        print("LF_PALANTIR_CLASS_EQ_PASS")

if __name__ == "__main__":
    main()
