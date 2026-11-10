"""Compile and run the ex7 visible check against target/classes (after mvn package)."""
import os
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
CLASSES = os.path.join(HERE, "..", "..", "target", "classes")
java = os.path.realpath(shutil.which("java") or "")
javac = os.path.join(os.path.dirname(java), "javac")
if not os.path.isdir(CLASSES) or not os.path.exists(javac):
    sys.exit("EX7_VISIBLE_PREREQ_MISSING (run mvn package first; javac must sit next to java)")
out = tempfile.mkdtemp()
src = os.path.join(HERE, "ReminderUpdateVisibleCheck.java")
subprocess.run([javac, "-d", out, "-cp", CLASSES, src], check=True)
subprocess.run([java, "-cp", CLASSES + os.pathsep + out, "ReminderUpdateVisibleCheck"], check=True)
