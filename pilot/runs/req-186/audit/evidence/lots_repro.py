"""Audit reproducer: which analysed requirements reached a lot, read at the closing commit."""
import json, subprocess, sys
BASE, ARGS = sys.argv[1], json.load(open(sys.argv[2]))
show = lambda p: json.loads(subprocess.run(["git", "show", f"{BASE}:{p}"], capture_output=True, text=True, check=True).stdout)
analysis, lots = show(ARGS["analysis"]), show(ARGS["lots"])
analysed = sorted({r["requirement_id"] for r in analysis["requirements"]})
in_lots = {l["area"]: sorted(l["requirement_ids"]) for l in lots["lots"]}
assigned = {r for ids in in_lots.values() for r in ids}
fronts = {f["execution_area"]: sorted(f["evidence_refs"]) for f in analysis["material_fronts"]}
print(json.dumps([
    {"case": "REQUIREMENTS_WITHOUT_LOT", "analysed": len(analysed), "missing": sorted(set(analysed) - assigned)},
    {"case": "BACKEND_FRONT_RULE_REFS", "refs": [r for r in fronts.get("BACKEND", []) if "reglas" in r]},
    {"case": "BACKEND_LOT_REQUIREMENTS", "ids": in_lots.get("BACKEND", [])},
    {"case": "CONTROL_ASSIGNED", "rule": ARGS["control"], "assigned": ARGS["control"] in assigned},
], ensure_ascii=False, indent=1))
