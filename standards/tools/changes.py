"""Circuito C9: cambios versionados, clasificación de diffs y deuda D11. Stdlib."""
import argparse
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path
from policy_invariants import NON_WAIVABLE

ROOT = Path(__file__).resolve().parents[2]
STD = ROOT / "standards"
CHANGES = STD / "changes"
BASELINE = STD / "baseline"
PINFILE = STD / "pins.json"
RE_CHANGE = re.compile(r"CHG-\d{4,}$")
SEMVER = re.compile(r"\d+\.\d+\.\d+$")
CLASSES = {"EDITORIAL","ADDITIVE","TIGHTENING","RELAXING","SECURITY"}
SECURITY_IDS = {"STD-GEN-03","STD-GEN-04","STD-DB-06","STD-DB-07","STD-API-04"}
CONSUMPTION_KEYS = {"pricing_version","policy_version","models","prices","cache_accounting","approved_for_use","source_url","checked_at","valid_from","valid_to","currency","unit","allowed_ttls","service_tier","input","output","cache_read","cache_write_by_ttl","mode","modes","budget","amount","warning_percent","decision_percent","unconfigured_action","unmeasured_at_warning","cost_precision","postgres","json","business_amounts","decision_refs","stable_context_cache","minimum_context","no_rediscovery","early_stop","difficulty_model_routing","standards","reviews","tests"}
KNOWN = {"catalog_version","glossary_version","registry_version","kit_version","schema_version","change_registry","status","scope","controls",
 "status","source","canonical_store_target","severity_values","enforcement_states",
 "legacy_policy","precedence","domains","decisions","rules","waiver_settings","level",
 "context_paths","technical_tokens","terms","spanish_check_paths","spanish_token_exclusions",
 "project","waivers","placeholders","files","id","rule","severity","enforcement",
 "waiver_policy","allowed","eligible_controls","reason","approvers","max_days",
 "linter_rule_max_days","test_fixture_max_days","linter_rule_denylist",
 "term_id","term_en","term_es","plural_en","definition","synonyms_es","rejected_en",
 "legacy_en","contexts","examples","good","bad","sources","decision_ref","notes",
 "values","match","except_after","form","contracts","state","command","tool",
 "planned_control","description","title","date","approver","reviewed_by","scope",
 "ref","topic","decision","adr","domain","lf_rule_refs","severity_condition",
 "status","path","sha256","project","status","waiver_id","target","catalog_version",
 "kind","requested_by","approved_by","approved_at","expires_at","evidence",
 "requested_at","supersedes","revoked_at","revocation_reason","paths","controls",
 "rule_id","rule","tool","from","to","name","version","action","status"}
VERSIONS = {"standards/catalog.json":"catalog_version",
 "standards/glossary/base.json":"glossary_version",
 "standards/glossary/projects/lf.json":"glossary_version",
 "standards/waivers/waivers.json":"registry_version",
 "standards/kit-base/kit.json":"kit_version",
 "standards/consumption/pricing.json":"pricing_version",
 "standards/consumption/policy.json":"policy_version"}
SHADOW = ["STD-FE-02","STD-GEN-05","STD-GEN-01","STD-GIT-01","STD-BE-05","STD-FE-07"]


def sha(data):
    return hashlib.sha256(data).hexdigest()


def git(*args):
    return subprocess.run(["git",*args],cwd=ROOT,text=True,capture_output=True,check=True).stdout.strip()


def json_at(ref,path):
    try:
        return json.loads(git("show",f"{ref}:{path}"))
    except subprocess.CalledProcessError:
        return None


def file_at(ref,path):
    try: return git("show",f"{ref}:{path}")
    except subprocess.CalledProcessError: return None


def version(v):
    if not isinstance(v,str) or not SEMVER.fullmatch(v):
        return None
    return tuple(int(n) for n in v.split("."))


def load_changes(root=CHANGES):
    records=[]
    for p in sorted(root.glob("CHG-*.json")):
        records.append((p,json.loads(p.read_text(encoding="utf8"))))
    return records


def validate_record(c):
    err=[]
    required={"schema_version","change_id","change_class","title","reason","trigger",
       "artifacts","affected","existing_code_impact","security_pin_invalidation",
       "requested_by","approved_by","evidence"}
    if c.keys() < required: err.append("INVALID_CHG_SCHEMA")
    if c.get("schema_version")!="LF_STANDARD_CHANGE_V1" or not RE_CHANGE.fullmatch(str(c.get("change_id",""))):
        err.append("INVALID_CHG_SCHEMA")
    kind=c.get("change_class")
    if kind not in CLASSES: err.append("INVALID_CHG_SCHEMA")
    if c.get("approved_by")!="paulozterra" or str(c.get("requested_by","")).startswith("agent:") and c.get("approved_by")==c.get("requested_by"):
        err.append("INVALID_APPROVER")
    if not isinstance(c.get("artifacts"),list): err.append("INVALID_CHG_SCHEMA")
    if kind=="RELAXING" and (not str(c.get("risk","")).strip() or not str(c.get("compensating_control","")).strip()):
        err.append("MISSING_RELAXING_EVIDENCE")
    if kind=="SECURITY":
        rev=c.get("independent_review")
        if not isinstance(rev,dict) or not all(rev.get(k) is not None for k in ("reviewed_sha256","reviewer_ref","separation_declaration","provider_attested")) or rev.get("provider_attested") is not False:
            err.append("INDEPENDENT_REVIEW_MISSING")
        elif rev["reviewed_sha256"]!=c.get("review_content_sha256"):
            err.append("REVIEW_STALE_SHA")
        if not c.get("security_pin_invalidation",{}).get("invalidates"):
            err.append("SECURITY_PIN_NOT_INVALIDATED")
    return sorted(set(err))


def validate_all(records):
    errs=[]; seen=set()
    for path,c in records:
        errs += validate_record(c)
        if c.get("change_id") in seen: errs.append("DUPLICATE_CHG_ID")
        seen.add(c.get("change_id"))
        if path.stem != c.get("change_id"): errs.append("INVALID_CHG_FILENAME")
    return sorted(set(errs))


def render(records):
    rows=["# Cambios del reglamento", "","> Generado desde standards/changes/CHG-NNNN.json; no editar manualmente.","",
          "| ID | Clase | Título | Artefactos | Aprobador previsto | PR |",
          "|---|---|---|---|---|---|"]
    for _,c in records:
        ars=", ".join(f"{a['artifact']} {a['from_version']} → {a['to_version']}" for a in c.get("artifacts",[]))
        rows.append(f"| {c['change_id']} | {c['change_class']} | {c.get('title','')} | {ars} | {c.get('approved_by','')} | {c.get('evidence',{}).get('pr_url','')} |")
    return "\n".join(rows)+"\n"


def normalized(obj,key=None):
    if isinstance(obj,list):
        identity={"rules":"id","terms":"term_id","waivers":"waiver_id"}.get(key)
        if identity and all(isinstance(x,dict) and identity in x for x in obj):
            return {x[identity]:normalized(x) for x in obj}
        return [normalized(x) for x in obj]
    if isinstance(obj,dict):
        return {k:normalized(v,k) for k,v in obj.items()}
    return obj


def walk(old,new,root=""):
    if old==new:return []
    if isinstance(old,dict) and isinstance(new,dict):
        return sum((walk(old.get(k),new.get(k),root+"/"+k) for k in old.keys()|new.keys()),[])
    return [(root,old,new)]


def security_rule(rule_id):
    return bool(rule_id.startswith(("STD-SEC-","STD-AUD-","STD-CONS-")) or rule_id in SECURITY_IDS)


def classify_fields(changes, path=""):
    flags=set(); warnings=[]; errors=[]
    for pointer,old,new in changes:
        parts=[x for x in pointer.split("/") if x]
        if not parts: continue
        allowed=KNOWN | (CONSUMPTION_KEYS if path.startswith("standards/consumption/") else set())
        if any(x not in allowed and not (x.startswith("STD-") or x.startswith("GLOSS-") or x.isdigit())
               for x in parts):
            errors.append("UNCLASSIFIED_FIELD_CHANGE"); continue
        if parts[-1] in ("catalog_version","glossary_version","registry_version","kit_version"):
            continue
        sec=next((x for x in parts if x.startswith("STD-")),None)
        tail=parts[-1]
        effect="EDITORIAL"
        if tail in ("rule","definition","title","description","notes","good","bad","examples"):
            warnings.append("PROSE_CHANGE_REVIEW")
            if sec and security_rule(sec):warnings.append("SECURITY_DOMAIN_PROSE_REVIEW")
        elif tail=="decisions" and isinstance(old,list) and isinstance(new,list) and new[:len(old)]==old:
            effect="ADDITIVE"
        elif tail in ("severity",):
            effect="TIGHTENING" if str(new) in ("BLOCK","BLOCK_OR_WARN") else "RELAXING"
        elif tail=="state":
            effect="TIGHTENING" if new=="active" else "ADDITIVE" if new=="shadow" else "RELAXING"
        elif tail=="allowed":
            effect="RELAXING" if new is True else "TIGHTENING"
            if sec in NON_WAIVABLE and new is True:errors.append("L1_WAIVER_PROHIBITED")
        elif path=="standards/consumption/policy.json" and tail in ("warning_percent","decision_percent"):
            effect="RELAXING" if new>old else "TIGHTENING"
        elif tail in ("max_days","linter_rule_max_days","test_fixture_max_days"):
            effect="RELAXING" if new is not None and old is not None and new>old else "TIGHTENING"
        elif tail=="linter_rule_denylist":
            effect="RELAXING" if isinstance(old,list) and isinstance(new,list) and set(new)<set(old) else "TIGHTENING"
        elif tail=="approvers":effect="SECURITY"
        elif tail in ("command","enforcement","waiver_policy","rejected_en","technical_tokens","spanish_token_exclusions"):
            effect="TIGHTENING"
        elif old is None and new is not None:effect="ADDITIVE"
        elif new is None and old is not None:effect="RELAXING"
        else:effect="TIGHTENING"
        if sec and security_rule(sec) and effect!="EDITORIAL":effect="SECURITY"
        if "waiver_settings" in parts and tail in ("approvers","linter_rule_denylist"):effect="SECURITY"
        flags.add(effect)
    if "RELAXING" in flags and "TIGHTENING" in flags:errors.append("MIXED_CHANGE_REQUIRES_SPLIT")
    ranked=["EDITORIAL","ADDITIVE","TIGHTENING","RELAXING","SECURITY"]
    return (max(flags,key=ranked.index) if flags else "EDITORIAL"), sorted(set(warnings)),sorted(set(errors))


def check_transition(base_objects,head_objects,changed_paths,chg=None):
    findings=[];warnings=[];flags=[]
    for path in changed_paths:
        if path in ("standards/CAMBIOS.md","standards/CATALOGO.md","standards/GLOSARIO.md","standards/WAIVERS.md"):
            if chg is None: findings.append("DERIVED_ONLY_EDIT")
            continue
        if path.startswith("standards/changes/"):
            continue
        if path in VERSIONS:
            old=base_objects.get(path);new=head_objects.get(path)
            if old is None and new is not None and path.startswith("standards/consumption/"):
                flags.append("ADDITIVE")
                if not chg or not any(a.get("path")==path and a.get("to_version")==new.get(VERSIONS[path]) for a in chg.get("artifacts",[])):
                    findings.append("MISSING_CHG")
                continue
            if old is None or new is None:
                findings.append("UNCLASSIFIED_FIELD_CHANGE");continue
            differences=walk(normalized(old),normalized(new))
            vfield=VERSIONS[path]; before=version(old.get(vfield));after=version(new.get(vfield))
            material=[x for x in differences if x[0]!="/"+vfield]
            if material and (not before or not after or after<=before):
                findings.append("VERSION_NOT_BUMPED")
            if not material and before!=after:findings.append("UNEXPLAINED_VERSION_BUMP")
            if path=="standards/consumption/pricing.json":
                before_rows={(r["provider"],r["model"],r["service_tier"],r["valid_from"]):r
                             for r in old.get("models",[])}
                after_rows={(r["provider"],r["model"],r["service_tier"],r["valid_from"]):r
                            for r in new.get("models",[])}
                for identity, prior in before_rows.items():
                    current=after_rows.get(identity)
                    if current is None or any(current.get(k)!=v for k,v in prior.items() if k!="valid_to") or (
                      prior.get("valid_to") is not None and (current or {}).get("valid_to")!=prior["valid_to"]):
                        findings.append("PRICE_ROW_REWRITE")
                    elif current["valid_to"] is not None and prior.get("valid_to") is None:
                        if current["valid_to"]<=current["valid_from"]:
                            findings.append("PRICE_ROW_REWRITE")
                if set(after_rows)-set(before_rows) and "PRICE_ROW_REWRITE" not in findings:
                    material=[("/models",None,"ADDED_PRICE_ROW")]
            category,warns,errs=classify_fields(material,path);warnings+=warns;findings+=errs
            if chg and (material or before!=after):
                covered=any(a.get("path")==path and a.get("from_version")==old.get(vfield)
                            and a.get("to_version")==new.get(vfield)
                            for a in chg.get("artifacts",[]))
                if not covered:findings.append("MISSING_CHG")
            if material:flags.append(category)
            if before and after and material:
                expected=(before[0],before[1],before[2]+1) if category=="EDITORIAL" else (before[0],before[1]+1,0)
                if after!=expected:findings.append("VERSION_NOT_BUMPED")
        elif (path.startswith("standards/tools/") and path.endswith(".py")
              or path == ".github/workflows/ci.yml"):
            flags.append("ADDITIVE")  # mínimo requerido; puede declararse una clase superior
        elif path == "standards/pins.json":
            old_min=(base_objects.get(path) or {}).get("minimum_safe_versions", {})
            new_min=(head_objects.get(path) or {}).get("minimum_safe_versions", {})
            raised=any(version(v) is not None and (
                old_min.get(k) is None or (version(old_min[k]) is not None and version(v)>version(old_min[k]))
            ) for k,v in new_min.items() if v is not None)
            flags.append("SECURITY" if raised else "ADDITIVE")
        elif path.startswith("standards/baseline/") and path.endswith(".json"):
            old_baseline=(base_objects.get(path) or {})
            new_baseline=(head_objects.get(path) or {})
            if new_baseline.get("count", 0)>old_baseline.get("count", 0) or set(new_baseline.get("fingerprints", []))-set(old_baseline.get("fingerprints", [])):
                findings.append("BASELINE_INCREASE")
        elif path.endswith(".md") and path.startswith("standards/"):
            if chg is None:findings.append("DERIVED_ONLY_EDIT")
    if flags and not chg:findings.append("MISSING_CHG")
    if chg:
        if "RELAXING" in flags and "TIGHTENING" in flags:findings.append("MIXED_CHANGE_REQUIRES_SPLIT")
        effective="SECURITY" if "SECURITY" in flags else "RELAXING" if "RELAXING" in flags else "TIGHTENING" if "TIGHTENING" in flags else "ADDITIVE" if "ADDITIVE" in flags else "EDITORIAL"
        declared=chg.get("change_class")
        protected_only=any(p.startswith("standards/tools/") or p==".github/workflows/ci.yml" for p in changed_paths)
        hierarchy={"EDITORIAL":0,"ADDITIVE":1,"TIGHTENING":2,"RELAXING":3,"SECURITY":4}
        if declared not in hierarchy or (protected_only and hierarchy[declared]<hierarchy["ADDITIVE"]) or (
                not protected_only and declared!=effective) or (
                protected_only and hierarchy[declared]<hierarchy[effective]):
            findings.append("CHANGE_CLASS_MISMATCH")
        findings+=validate_record(chg)
    return {"detected_class":flags,"warnings":sorted(set(warnings)),
            "findings":sorted(set(findings)),"verdict":"FAIL" if findings else "PASS"}


def baseline_fingerprint(rule_id,path,reason_code,line):
    normalized_line=" ".join(line.strip().split())
    return sha((rule_id+path+reason_code+normalized_line).encode("utf8"))


def baseline_check(baselines,now):
    errors=[]
    for rule,data in baselines.items():
        previous=set(data["fingerprints"]); current=set(now.get(rule,[]))
        if len(current)>data["count"] or current-previous:errors.append("BASELINE_INCREASE")
    return sorted(set(errors))


def review_content_digest(base):
    """Huella de contenido revisable excluyendo el CHG auto-referencial."""
    changed=git("diff","--name-only",base,"HEAD").splitlines()
    items=[]
    for path in sorted(changed):
        if path.startswith("standards/changes/"):
            continue
        file=ROOT/path
        if file.is_file():
            items.append(path.encode("utf8")+b"\0"+hashlib.sha256(file.read_bytes()).digest())
        else:
            items.append(path.encode("utf8")+b"\0deleted")
    return sha(b"\n".join(items))


def measured_shadow_findings(ref):
    """Mide de forma reproducible fuentes reales, no acepta contadores inventados."""
    import glossary
    import waivers
    records={rule:[] for rule in SHADOW}
    gl=glossary.load()
    scanner=glossary.Scanner(gl)
    paths=git("ls-tree","-r","--name-only",ref,"--","backend/src","frontend/src").splitlines()
    for path in paths:
        if ref=="HEAD" and (ROOT/path).is_file():
            content=(ROOT/path).read_text(encoding="utf8",errors="replace")
        else:
            content=file_at(ref,path)
        if content is None:continue
        lines=content.splitlines()
        if path.startswith("frontend/src/") and Path(path).suffix in (".ts",".tsx",".js",".jsx",".mjs",".css"):
            stem=Path(path).name.split(".")[0]
            if not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*",stem) and Path(path).name!="next-env.d.ts":
                records["STD-FE-02"].append(baseline_fingerprint("STD-FE-02",path,"INVALID_FILENAME",Path(path).name))
        if Path(path).suffix in (".ts",".tsx",".js",".jsx",".mjs",".java",".py"):
            for number,line in enumerate(lines,1):
                if waivers.SUPPRESS.search(line) and not waivers.REF.search(line):
                    records["STD-GEN-05"].append(baseline_fingerprint("STD-GEN-05",path,"NO_WAIVER",line))
        for item in scanner.scan(path,content):
            match=re.search(r":(\d+):",item)
            if match:
                number=int(match.group(1))
                original=lines[number-1] if number<=len(lines) else item
                records["STD-GEN-01"].append(baseline_fingerprint("STD-GEN-01",path,"SPANISH_OR_REJECTED",original))
    # Rama no es archivo histórico: STD-GIT-01 se evalúa en el job sombra,
    # pero no se inventan hallazgos históricos para main.
    return {k:sorted(set(v)) for k,v in records.items()}


def compare_measured_baseline(records,prior,head):
    issues=[]
    for rule,info in records.items():
        if info.get("measurement")=="NOT_MEASURED_UNTIL_C10":
            continue
        expected=sorted(info["fingerprints"])
        if info["count"]!=len(expected):
            issues.append("BASELINE_INCREASE")
        if prior.get(rule,[])!=expected:
            issues.append("BASELINE_MISMATCH")
        if len(head.get(rule,[]))>info["count"] or set(head.get(rule,[]))-set(expected):
            issues.append("BASELINE_INCREASE")
    # Formateadores sin huellas: NOT_MEASURED es informativo, no bloquea.
    return sorted(set(issues))


def compare_baseline_ref(base,records):
    return compare_measured_baseline(records,measured_shadow_findings(base),measured_shadow_findings("HEAD"))


def check_pins(pins,previous=None):
    errors=[]
    for name,minimum in pins.get("minimum_safe_versions",{}).items():
        if minimum is not None and version(minimum) is None:errors.append("INVALID_PIN_VERSION")
        if previous and previous.get("minimum_safe_versions",{}).get(name) is not None:
            before=version(previous["minimum_safe_versions"][name])
            after=version(minimum)
            if after is None or after<before:errors.append("PIN_MINIMUM_DECREASED")
    return errors


def report(errors,**more):
    result={"findings":[{"reason_code":x} for x in sorted(set(errors))],
            "verdict":"FAIL" if errors else "PASS",**more}
    print(json.dumps(result,ensure_ascii=False))
    return int(bool(errors))


def main(argv=None):
    p=argparse.ArgumentParser()
    sub=p.add_subparsers(dest="cmd",required=True)
    sub.add_parser("validate")
    r=sub.add_parser("render");r.add_argument("--check",action="store_true")
    for cmd in ("classify","check","baseline-check"):
        s=sub.add_parser(cmd);s.add_argument("--base",required=True)
    pin=sub.add_parser("pin-check");pin.add_argument("--artifact",required=True);pin.add_argument("--version",required=True)
    a=p.parse_args(argv)
    records=load_changes()
    if a.cmd=="validate":return report(validate_all(records))
    if a.cmd=="render":
        rendered=render(records);dest=STD/"CAMBIOS.md"
        if a.check:return report([] if dest.exists() and dest.read_text(encoding="utf8")==rendered else ["DERIVED_VIEW_STALE"])
        dest.write_text(rendered,encoding="utf8");return report([])
    if a.cmd=="pin-check":
        pins=json.loads(PINFILE.read_text(encoding="utf8"))
        minimum=pins["minimum_safe_versions"].get(a.artifact)
        return report(["PIN_INVALIDATED_SECURITY"] if minimum and (version(a.version) is None or version(a.version)<version(minimum)) else [],
                      artifact=a.artifact,minimum_safe_version=minimum)
    base=git("merge-base",a.base,"HEAD")
    changed=git("diff","--name-only",base,"HEAD").splitlines()
    base_data={path:json_at(base,path) for path in changed if path in VERSIONS or path=="standards/pins.json" or path.startswith("standards/baseline/")}
    head_data={path:json.loads((ROOT/path).read_text(encoding="utf8")) for path in changed if (path in VERSIONS or path=="standards/pins.json" or path.startswith("standards/baseline/")) and (ROOT/path).exists()}
    introduced=[c for _,c in records if file_at(base,"standards/changes/"+c["change_id"]+".json") is None]
    if a.cmd in ("classify","check"):
        result=check_transition(base_data,head_data,changed,introduced[0] if len(introduced)==1 else None)
        errors=list(result["findings"])
        if len(introduced)>1:errors.append("MULTIPLE_CHG_IN_PR")
        if a.cmd=="check":
            errors+=validate_all(records)
            bpin=json_at(base,"standards/pins.json")
            hpin=json.loads(PINFILE.read_text(encoding="utf8"))
            errors+=check_pins(hpin,bpin)
            kit=json.loads((STD/"kit-base/kit.json").read_text(encoding="utf8"))
            cat=json.loads((STD/"catalog.json").read_text(encoding="utf8"))
            gloss=json.loads((STD/"glossary/base.json").read_text(encoding="utf8"))
            for old_v,current_v in ((kit["catalog_version"],cat["catalog_version"]),
                                    (kit["glossary_version"],gloss["glossary_version"])):
                if version(old_v) is None or version(current_v) is None or version(old_v)>version(current_v):
                    errors.append("KIT_PIN_INCOMPATIBLE")
            if introduced and introduced[0].get("change_class")=="SECURITY":
                review=introduced[0].get("independent_review") or {}
                if review.get("reviewed_sha256")!=review_content_digest(base):
                    errors.append("REVIEW_STALE_SHA")
                current=hpin.get("minimum_safe_versions",{})
                previous=(bpin or {}).get("minimum_safe_versions",{})
                artifacts=[a.get("artifact") for a in introduced[0].get("artifacts",[])]
                if not any(current.get(a) is not None and
                           (previous.get(a) is None or version(current[a])>version(previous[a]))
                           for a in artifacts):
                    errors.append("SECURITY_PIN_NOT_INVALIDATED")
        return report(errors,detected_class=result["detected_class"],warnings=result["warnings"],base_sha=base)
    if a.cmd=="baseline-check":
        baseline={p.stem:json.loads(p.read_text(encoding="utf8")) for p in BASELINE.glob("*.json")}
        # New or modified source findings are rejected by the existing diff scanners.
        # Historical fingerprint comparison requires same scanner version on both refs.
        errors=compare_baseline_ref(base,baseline)
        return report(errors,baseline_rules=len(baseline),not_measured=[r for r,v in baseline.items() if v.get("measurement")=="NOT_MEASURED_UNTIL_C10"],base_sha=base)


if __name__=="__main__":
    sys.exit(main())
