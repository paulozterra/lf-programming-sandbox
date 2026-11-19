"""T57: every live workflow that runs Maven uses the Central mirror first.

Maven Central rate-limits (HTTP 429) shared GitHub runner IPs; on 16/11 and
19/11 the CI, Worker and exams failed resolving Spring Boot artifacts. The
mirror is written to Maven's *global* settings so it also applies to the
vendored Worker and exams, which run mvn with an isolated, empty HOME.
Central stays as fallback (profile repositories are tried before it).
"""
from pathlib import Path
import re
import xml.etree.ElementTree as ET

import yaml

ROOT = Path(__file__).resolve().parents[1]
LIVE = ("ci.yml", "worker-native.yml", "exam-rehearsal.yml", "pg37-evidence.yml")
STEP = "Maven Central mirror with Central fallback (T57)"
MIRROR = "https://maven-central.storage-download.googleapis.com/maven2/"


def _steps(workflow):
    data = yaml.safe_load((ROOT / ".github/workflows" / workflow).read_text("utf-8"))
    for name, job in data["jobs"].items():
        yield name, job.get("steps", [])


def _mirror_steps():
    for workflow in LIVE:
        for job, steps in _steps(workflow):
            for step in steps:
                if step.get("name") == STEP:
                    yield workflow, job, step


def test_every_live_java_job_sets_the_mirror_right_after_setup_java():
    for workflow in LIVE:
        for job, steps in _steps(workflow):
            for i, step in enumerate(steps):
                if "actions/setup-java@" in str(step.get("uses", "")):
                    assert steps[i + 1].get("name") == STEP, (workflow, job)


def test_all_mirror_steps_are_identical():
    runs = {step["run"] for _, _, step in _mirror_steps()}
    assert len(runs) == 1
    assert len(list(_mirror_steps())) >= 6


def test_settings_xml_is_valid_and_keeps_central_as_fallback():
    run = next(_mirror_steps())[2]["run"]
    xml = re.search(r"<<'XML'\n(.*?)\nXML\n", run, re.S).group(1)
    root = ET.fromstring(xml)
    ns = {"m": "http://maven.apache.org/SETTINGS/1.2.0"}
    urls = [e.text for e in root.iterfind(".//m:url", ns)]
    assert urls == [MIRROR, MIRROR]  # repositories + pluginRepositories
    # No <mirrors>: a mirrorOf=central would remove the Central fallback.
    assert root.find("m:mirrors", ns) is None
    assert [e.text for e in root.iterfind(".//m:activeProfile", ns)] == ["lf-maven-mirror"]
    assert all(e.text == "false" for e in root.iterfind(".//m:snapshots/m:enabled", ns))
