"""Audit reproducer (req-286): Analysis area table and HEX values, read at the closing commit."""
import json, re, subprocess, sys
BASE = sys.argv[1]
show = lambda p: subprocess.run(["git", "show", f"{BASE}:{p}"], capture_output=True, text=True, check=True).stdout
areas = json.loads(show("analysis/a9/area_rules_v1.json"))["section_areas"]
lots = {l["area"]: set(l["requirement_ids"]) for l in json.loads(show("pilot/runs/req-286/lots.json"))["lots"]}
screen_rules = ["REQ-SBX-B2B-R-ERROR-SAFE-MESSAGE", "REQ-SBX-B2B-R-UX-PASSWORD-VISIBILITY", "REQ-SBX-B2B-R-UX-PASSWORD-MANAGERS"]
hexre = re.compile(r"#[0-9A-Fa-f]{6}\b")
out = [
 {"case": "AREA_errors_fields", "errors": areas["errors"], "fields": areas["fields"], "visual.variants": areas["visual.variants"]},
 {"case": "AREA_screen_rules_lot", "in_backend": [r for r in screen_rules if r in lots["BACKEND"]],
  "in_frontend": [r for r in screen_rules if r in lots["FRONTEND"]]},
 {"case": "AREA_control_api_rule", "AUTH-ENVELOPE_in_backend": "REQ-SBX-B2B-R-AUTH-ENVELOPE" in lots["BACKEND"],
  "AUTH-ENVELOPE_in_frontend": "REQ-SBX-B2B-R-AUTH-ENVELOPE" in lots["FRONTEND"]},
 {"case": "HEX_lib", "count": len(hexre.findall(show("frontend/src/lib/sbx-b2b-login.ts")))},
 {"case": "HEX_control_page", "count": len(hexre.findall(show("frontend/src/app/sbx-b2b-login/page.tsx")))},
]
print(json.dumps(out, indent=1))
