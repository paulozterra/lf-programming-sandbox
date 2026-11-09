#!/usr/bin/env python3
"""EX6 deterministic N+1 AOSP remediation, matching CHG-0015 policy.

No model, no secrets. Only the three original EX6 new Java files. Compile
original and formatted complete app with javac -g:none and compare EVERY
class path and class byte SHA before writing. Source N remains immutable.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import pathlib
import shutil
import subprocess
import tempfile
import urllib.request

ORIGINAL="912c4ad9ea71f48edbd1ac58089441f9ed2c3449"
J="apps/time-service/src/main/java/lf/sandbox/time/reminder"
FILES=tuple(J+"/"+x for x in
    ("ReminderStats.java","ReminderStatsService.java","ReminderStatsController.java"))
SRC="apps/time-service/src/main/java"
POM="apps/time-service/pom.xml"
GJF_VERSION="1.30.0"
GJF_SHA256="f2239a8a234a240a54fdff7809d4b3e66702c21f590c77a0b6cf7b20c829e95a"
URL="https://github.com/google/google-java-format/releases/download/v1.30.0/google-java-format-1.30.0-all-deps.jar"

def require(cond,code):
    if not cond:
        raise RuntimeError("EX6_FORMAT_N1_BLOCK:"+code)

def run(argv,cwd,timeout=400):
    x=subprocess.run(argv,cwd=cwd,capture_output=True,timeout=timeout)
    if x.returncode!=0:
        raise RuntimeError("EX6_FORMAT_N1_COMMAND_FAILED:"+argv[0]+":"+str(x.returncode)+
            "\n"+x.stderr.decode(errors="replace")[-1500:])
    return x.stdout

def git(root,*args):
    return run(["git","-C",str(root),*args],cwd=root).decode().strip()

def classes(root,out,cp):
    sources=sorted((root/SRC).rglob("*.java"))
    require(bool(sources),"NO_JAVA")
    out.mkdir(parents=True)
    run(["javac","--release","21","-g:none","-encoding","UTF-8",
         "-cp",cp,"-d",str(out),*[str(p) for p in sources]],cwd=root)
    found={p.relative_to(out).as_posix():hashlib.sha256(p.read_bytes()).hexdigest()
           for p in out.rglob("*.class")}
    require(bool(found),"NO_CLASS_FILES")
    return found

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--root",type=pathlib.Path,default=pathlib.Path("."))
    ap.add_argument("--out",type=pathlib.Path,required=True)
    ap.add_argument("--apply",action="store_true")
    a=ap.parse_args()
    root=a.root.resolve()
    require(git(root,"rev-parse","HEAD")!=ORIGINAL or a.apply,"HEAD_ORIGINAL_N")
    require(not git(root,"status","--porcelain"),"DIRTY_WORKTREE")
    require(all((root/x).is_file() for x in FILES),"EX6_SOURCE_MISSING")
    for x in FILES:
        base=git(root,"rev-parse",ORIGINAL+":"+x)
        head=git(root,"rev-parse","HEAD:"+x)
        require(base==head,"EX6_SOURCE_DRIFT:"+x)
    with tempfile.TemporaryDirectory(prefix="ex6_format_n1_") as t:
        tmp=pathlib.Path(t)
        jar=tmp/"google-java-format.jar"
        request=urllib.request.Request(URL,headers={"User-Agent":"LF-EX6-CHG0022"})
        with urllib.request.urlopen(request,timeout=90) as response:
            data=response.read(8_000_000)
        require(hashlib.sha256(data).hexdigest()==GJF_SHA256,"FORMATTER_PIN_MISMATCH")
        jar.write_bytes(data)
        old=tmp/"old"
        new=tmp/"new"
        for item in (old,new):
            shutil.copytree(root/"apps/time-service",item/"apps/time-service",
                            ignore=shutil.ignore_patterns("target",".git"))
        selected=[new/x for x in FILES]
        run(["java","-jar",str(jar),"--aosp","--replace",*[str(x) for x in selected]],cwd=new)
        run(["java","-jar",str(jar),"--aosp","--dry-run",
             "--set-exit-if-changed",*[str(x) for x in selected]],cwd=new)
        cp_file=tmp/"classpath.txt"
        run(["mvn","-B","-q","-f",POM,"dependency:build-classpath",
             "-Dmdep.outputFile="+str(cp_file)],cwd=root)
        cp=cp_file.read_text().strip()
        original_classes=classes(old,tmp/"oldclasses",cp)
        formatted_classes=classes(new,tmp/"newclasses",cp)
        require(original_classes==formatted_classes,"CLASS_BYTES_DIFFER")
        changed=[x for x in FILES if (old/x).read_bytes()!=(new/x).read_bytes()]
        require(set(changed)==set(FILES),"CHANGED_JAVA_SET_MISMATCH")
        a.out.mkdir(parents=True,exist_ok=False)
        for rel in FILES:
            dest=a.out/rel
            dest.parent.mkdir(parents=True,exist_ok=True)
            dest.write_bytes((new/rel).read_bytes())
        receipt={"schema_version":"EX6_AOSP_N1_CLASS_EQUIVALENCE_V1",
                 "original":ORIGINAL,"formatter_version":GJF_VERSION,
                 "formatter_sha256":GJF_SHA256,
                 "flags":["--aosp"],"changed_paths":list(FILES),
                 "class_sha256_before":original_classes,
                 "class_sha256_after":formatted_classes,
                 "class_count":len(original_classes),"class_bytes_identical":True,
                 "model_calls":0,"production_authority":False}
        raw=(json.dumps(receipt,sort_keys=True,separators=(",",":"))+"\n").encode()
        (a.out/"ex6-n1-class-equivalence.json").write_bytes(raw)
        (a.out/"ex6-n1-class-equivalence.sha256").write_text(
            hashlib.sha256(raw).hexdigest()+"  ex6-n1-class-equivalence.json\n")
        if a.apply:
            for rel in FILES:
                (root/rel).write_bytes((new/rel).read_bytes())
            require(set(git(root,"diff","--name-only").splitlines())==set(FILES),
                    "WORKTREE_CHANGED_PATHS_DRIFT")
        print("EX6_N1_AOSP_CLASS_BYTES_IDENTICAL_PASS")
        print("EX6_N1_CLASS_COUNT="+str(len(original_classes)))
        print("EX6_N1_CHANGES="+str(len(changed)))
        print("EX6_N1_NO_MODEL_TRUE")
if __name__=="__main__":
    main()
