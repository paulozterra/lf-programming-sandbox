#!/usr/bin/env python3
"""CHG-0022: independent N→N+1 exact 3-file AOSP and full .class byte gate."""
from __future__ import annotations
import hashlib
import pathlib
import shutil
import subprocess
import tempfile
import urllib.request
from format_remediation_n1 import (
    ORIGINAL, FILES, SRC, POM, GJF_SHA256, URL, require, run, git, classes,
)
ROOT=pathlib.Path(__file__).resolve().parents[2]

def main():
    require(not git(ROOT,"status","--porcelain"),"DIRTY_HEAD")
    # Original N must remain the original source of formatter input.
    require(git(ROOT,"rev-parse",ORIGINAL+"^{commit}")==ORIGINAL,"ORIGINAL_N_NOT_IN_GIT")
    actual=set(git(ROOT,"diff","--name-only",ORIGINAL,"HEAD","--",SRC).splitlines())
    require(actual==set(FILES),"N1_JAVA_CHANGED_SCOPE_NOT_EXACT_THREE")
    for path in FILES:
        require(git(ROOT,"cat-file","-e",ORIGINAL+":"+path)=="",
                "N_SOURCE_MISSING:"+path)
    with tempfile.TemporaryDirectory(prefix="ex6_n1_ci_") as work:
        temp=pathlib.Path(work)
        old=temp/"old"
        expected=temp/"expected"
        for dest in (old,expected):
            shutil.copytree(ROOT/"apps/time-service",dest/"apps/time-service",
                            ignore=shutil.ignore_patterns("target",".git"))
            for p in FILES:
                (dest/p).write_bytes(subprocess.check_output(
                    ["git","-C",str(ROOT),"show",ORIGINAL+":"+p]))
        jar=temp/"gjf.jar"
        req=urllib.request.Request(URL,headers={"User-Agent":"LF-EX6-CHG0022-CI"})
        with urllib.request.urlopen(req,timeout=90) as stream:
            data=stream.read(8_000_000)
        require(hashlib.sha256(data).hexdigest()==GJF_SHA256,"FORMATTER_PIN")
        jar.write_bytes(data)
        run(["java","-jar",str(jar),"--aosp","--replace",
             *[str(expected/p) for p in FILES]],cwd=expected)
        for path in FILES:
            require((expected/path).read_bytes()==(ROOT/path).read_bytes(),
                    "NOT_EXACT_FORMAT:"+path)
        run(["java","-jar",str(jar),"--aosp","--dry-run",
             "--set-exit-if-changed",*[str(ROOT/p) for p in FILES]],cwd=ROOT)
        cp_file=temp/"cp.txt"
        run(["mvn","-B","-q","-f",POM,"dependency:build-classpath",
             "-Dmdep.outputFile="+str(cp_file)],cwd=ROOT)
        cp=cp_file.read_text().strip()
        before=classes(old,temp/"base_classes",cp)
        after=classes(ROOT,temp/"new_classes",cp)
        require(before==after,"BYTE_IDENTICAL_CLASS_VERIFICATION_FAILED")
        print("EX6_N1_EXACT_AOSP_THREE_FILES_PASS")
        print("EX6_N1_JAVAC_G_NONE_CLASS_BYTES_IDENTICAL_PASS")
        print("EX6_N1_CLASS_COUNT="+str(len(before)))
        print("EX6_N1_PRODUCTION_AUTHORITY=false")

if __name__=="__main__":
    main()
