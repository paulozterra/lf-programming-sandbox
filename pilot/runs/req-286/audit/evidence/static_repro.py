"""Audit reproducer: Analysis area table and HEX values, read at the closing commit."""
import json, re, subprocess, sys
BASE = sys.argv[1]
ARGS = json.load(open(sys.argv[2]))  # case-specific ids live in data, not in route code
screen_rules, control = ARGS["screen_rules"], ARGS["api_control_rule"]
lots_file, page, lib = ARGS["lots"], ARGS["page"], ARGS["lib"]
show = lambda p: subprocess.run(["git", "show", f"{BASE}:{p}"], capture_output=True, text=True, check=True).stdout
areas = json.loads(show("analysis/a9/area_rules_v1.json"))["section_areas"]
lots = {l["area"]: set(l["requirement_ids"]) for l in json.loads(show(lots_file))["lots"]}
hexre = re.compile(r"#[0-9A-Fa-f]{6}\b")
out = [
 {"case": "AREA_errors_fields", "errors": areas["errors"], "fields": areas["fields"], "visual.variants": areas["visual.variants"]},
 {"case": "AREA_screen_rules_lot", "in_backend": [r for r in screen_rules if r in lots["BACKEND"]],
  "in_frontend": [r for r in screen_rules if r in lots["FRONTEND"]]},
 {"case": "AREA_control_api_rule", "rule": control, "in_backend": control in lots["BACKEND"],
  "in_frontend": control in lots["FRONTEND"]},
 {"case": "HEX_lib", "count": len(hexre.findall(show(lib)))},
 {"case": "HEX_control_page", "count": len(hexre.findall(show(page)))},
]
print(json.dumps(out, indent=1))
