#!/usr/bin/env python3
"""Temporary offline-only EX8 native proposal builder; exists ONLY on auxiliary branch."""
from __future__ import annotations
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile

CONTROL = Path.cwd()
BASE = "7a6c3eaea4442c6c3c518a2f33dfdf081b97b62b"
PREFIX = "apps/time-service/src/main/java/lf/sandbox/time/reminder/"
ALLOWED = tuple(PREFIX + name for name in (
    "ReminderRepository.java", "InMemoryReminderRepository.java", "ReminderController.java"
))

def run(*args, cwd=None, capture=False):
    p = subprocess.run(args, cwd=cwd or CONTROL, text=True, capture_output=capture)
    if p.returncode:
        if capture:
            print("FAILED:", args, p.stderr[-3000:], p.stdout[-2000:], file=sys.stderr)
        raise SystemExit(p.returncode)
    return p.stdout if capture else ""

def replace_once(value, old, new, name):
    if value.count(old) != 1:
        raise RuntimeError("SOURCE_DRIFT:" + name + ":" + str(value.count(old)))
    return value.replace(old, new, 1)

with tempfile.TemporaryDirectory(prefix="lf_ex8_native_") as tmp:
    temp = Path(tmp)
    source = temp / "source"
    run("git", "worktree", "add", "--detach", str(source), BASE)
    if run("git", "rev-parse", "HEAD", cwd=source, capture=True).strip() != BASE:
        raise RuntimeError("BASE_DRIFT")

    registration = json.loads((CONTROL / "pilot/worker_v08/native_tasks/ex8.json").read_text())
    task = registration["task_spec"]
    if task["base_head_sha"] != BASE or set(task["write_path_patterns"]) != set(ALLOWED):
        raise RuntimeError("REGISTERED_SCOPE_OR_BASE_DRIFT")
    spec = temp / "ex8-task-only.json"
    spec.write_text(json.dumps(task, sort_keys=True), encoding="utf-8")
    pack = temp / "ex8-pack.json"
    output = run(sys.executable, str(CONTROL / "pilot/worker_v08/export_task_pack.py"),
                 "--repo", str(source), "--task-spec", str(spec),
                 "--out", str(pack), capture=True)
    task_sha = hashlib.sha256(pack.read_bytes()).hexdigest()
    if task_sha not in output:
        raise RuntimeError("TASK_PACK_SHA_NOT_VERIFIED")
    package = json.loads(pack.read_text())
    flat = json.dumps(package, ensure_ascii=False)
    for required in ("REM-F1", "REM-F2", "STD-BE-05", "prog_backend_exp", "SPRINGBOOT_EXP"):
        if required not in flat:
            raise RuntimeError("TASK_PACK_CONTEXT_MISSING:" + required)
    print("EX8_EXPORTED_TASK_PACK_SHA256=" + task_sha)
    print("EX8_CONTEXT_PROFILE_SKILL_STD_BE_05_PASS")

    p = source / ALLOWED[0]
    raw = p.read_text(encoding="utf-8")
    raw = replace_once(raw, "    Optional<Reminder> update(long id, String text, LocalTime at);\n}",
                       "    Optional<Reminder> update(long id, String text, LocalTime at);\n\n"
                       "    Optional<Reminder> snooze(long id, int minutes);\n}", p.name)
    p.write_text(raw, encoding="utf-8")

    p = source / ALLOWED[1]
    raw = p.read_text(encoding="utf-8")
    method = '''
    @Override
    public synchronized Optional<Reminder> snooze(long id, int minutes) {
        if (minutes < 1 || minutes > 1440) {
            throw new IllegalArgumentException("minutes must be between 1 and 1440");
        }
        for (int i = 0; i < reminders.size(); i++) {
            Reminder existing = reminders.get(i);
            if (existing.id() == id) {
                LocalTime newTime = existing.at().plusMinutes(minutes);
                if (duplicates(id, existing.text(), newTime)) {
                    throw new IllegalStateException("duplicate reminder");
                }
                Reminder updated = new Reminder(id, existing.text(), newTime);
                reminders.set(i, updated);
                return Optional.of(updated);
            }
        }
        return Optional.empty();
    }

'''
    raw = replace_once(raw, "    @Override\n    public synchronized List<Reminder> findAll() {",
                       method + "    @Override\n    public synchronized List<Reminder> findAll() {", p.name)
    p.write_text(raw, encoding="utf-8")

    p = source / ALLOWED[2]
    raw = p.read_text(encoding="utf-8")
    method = '''
    @PostMapping("/api/reminders/{id}/snooze")
    public ResponseEntity<Object> snooze(
            @PathVariable String id, @RequestParam(name = "minutes", required = false) String minutes) {
        final long reminderId;
        final int amount;
        if (minutes == null || !minutes.matches("[0-9]+")) {
            return ResponseEntity.badRequest().build();
        }
        try {
            reminderId = Long.parseLong(id);
            amount = Integer.parseInt(minutes);
        } catch (NumberFormatException e) {
            return ResponseEntity.badRequest().build();
        }
        try {
            return repository.snooze(reminderId, amount)
                    .<ResponseEntity<Object>>map(r -> ResponseEntity.ok(toResponse(r)))
                    .orElseGet(() -> ResponseEntity.notFound().build());
        } catch (IllegalArgumentException e) {
            return ResponseEntity.badRequest().build();
        } catch (IllegalStateException e) {
            return ResponseEntity.status(409).build();
        }
    }

'''
    raw = replace_once(raw, "    // A variable {id} PUT mapping would otherwise turn PUT /stats into 400.\n",
                       method + "    // A variable {id} PUT mapping would otherwise turn PUT /stats into 400.\n", p.name)
    p.write_text(raw, encoding="utf-8")

    print("EX8_SOURCE_EDIT_SCOPE=ReminderRepository,InMemoryReminderRepository,ReminderController")
    run("mvn", "-B", "-q", "-f", "apps/time-service/pom.xml", "spotless:apply", cwd=source)
    changed = run("git", "diff", "--name-only", cwd=source, capture=True).splitlines()
    if set(changed) != set(ALLOWED):
        raise RuntimeError("WRITTEN_PATHS_DRIFT:" + repr(changed))
    print("EX8_PALANTIR_APPLIED_EXACTLY_3_ALLOWED_JAVA")
    run("mvn", "-B", "-q", "-f", "apps/time-service/pom.xml", "spotless:check", cwd=source)
    print("EX8_STD_BE_05_SPOTLESS_CHECK_PASS")
    run("mvn", "-B", "-q", "-f", "apps/time-service/pom.xml", "package", cwd=source)
    print("EX8_MAVEN_PACKAGE_AND_EXISTING_TESTS_PASS")
    run(sys.executable, "apps/time-service/visible-tests/ex8/run_visible.py", cwd=source)
    print("EX8_VISIBLE_TESTS_PASS")
    for older in ("ex7", "ex6"):
        script = source / "apps/time-service/visible-tests" / older / "run_visible.py"
        if script.is_file():
            run(sys.executable, str(script), cwd=source)
            print("EX8_REGRESSION_" + older.upper() + "_PASS")
    # Additional self-contained behavioral regression outside source; not a hidden oracle.
    cp = source / "apps/time-service/target/classes"
    extra = temp / "Ex8ExtraVisible.java"
    extra.write_text("""
import java.time.LocalTime;
import lf.sandbox.time.reminder.*;
public class Ex8ExtraVisible {
  public static void main(String[] args) {
    var r = new InMemoryReminderRepository();
    var a = r.save("Water", LocalTime.of(23,50,27));
    if (!r.snooze(a.id(),15).orElseThrow().at().equals(LocalTime.of(0,5,27))) throw new AssertionError("midnight_seconds");
    var b = r.save("water", LocalTime.of(0,10,27));
    try { r.snooze(a.id(),5); throw new AssertionError("duplicate"); }
    catch (IllegalStateException expected) { }
    if (!r.findById(a.id()).orElseThrow().at().equals(LocalTime.of(0,5,27))) throw new AssertionError("atomic");
    if (!r.snooze(a.id(),1440).orElseThrow().at().equals(LocalTime.of(0,5,27))) throw new AssertionError("same_self");
    try { r.snooze(999,0); throw new AssertionError("invalid_priority"); }
    catch (IllegalArgumentException expected) { }
    if (r.findAll().size()!=2 || r.findAll().get(0).id()!=a.id()) throw new AssertionError("order");
    System.out.println("EX8_EXTRA_VISIBLE_OK");
  }
}
""",encoding="utf-8")
    run("javac", "-cp", str(cp), "-d", str(temp), str(extra), cwd=source)
    run("java", "-cp", str(cp) + os.pathsep + str(temp), "Ex8ExtraVisible", cwd=source)
    print("EX8_ADDITIONAL_VISIBLE_REGRESSION_PASS")

    patch = run("git", "diff", "--no-ext-diff", "--", *ALLOWED, cwd=source, capture=True)
    if len(patch.encode()) > task["max_patch_bytes"] or patch.count("diff --git ") != 3:
        raise RuntimeError("EX8_PATCH_SIZE_OR_FILE_COUNT_INVALID")
    proposal = {
       "schema_version": 1,
       "summary": "REM-F1..F4: synchronized snooze, strict decimal HTTP validation, duplicate protection and Palantir formatting",
       "patch": patch,
       "changed_paths": sorted(ALLOWED),
    }
    sys.path.insert(0, str(CONTROL / "vendor/programming-agent/src"))
    from programming_agent_runner.hashutil import canonical_json_bytes
    proposal_sha = hashlib.sha256(canonical_json_bytes(proposal)).hexdigest()
    envelope = {"author":"GPT_NATIVE", "proposal":proposal,
                "proposal_sha256":proposal_sha, "task_pack_sha256":task_sha}
    out = temp / "ex8-proposal.json"
    out.write_bytes(canonical_json_bytes(envelope) + b"\n")
    print("EX8_PROPOSAL_SHA256="+proposal_sha)
    print("EX8_PROPOSAL_BYTES="+str(out.stat().st_size))
    print("EX8_ENVELOPE_JSON="+out.read_text(encoding="utf-8").strip())
    print("EX8_PREFLIGHT_PASS")
