"""Offline V1 skill resolver; does not call a model."""
import argparse,hashlib,json,re,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
STD=ROOT/"standards";DIR=STD/"skills"
SLUGS=("spring-boot","nextjs","postgres-flyway")
EXCLUDED_V1_DOMAINS=frozenset({"STD-PY","STD-SB","STD-IAC","STD-CONT"})
def digest(raw):return hashlib.sha256(raw).hexdigest()
def load_json(p):return json.loads(p.read_text(encoding="utf-8"))
def violations(skill,text,catalog,checks):
    errs=[]
    if not skill.get("catalog_compat"):errs.append("MISSING_SKILL_CATALOG_VERSION")
    if not skill.get("glossary_compat"):errs.append("MISSING_SKILL_GLOSSARY_VERSION")
    if skill.get("check_set_ref") not in checks["sets"]:errs.append("COMMAND_DRIFT")
    known={r["id"] for r in catalog["rules"]}
    if any(x["rule_id"] not in known or not x.get("reason") for x in skill["exclude_rule_ids"]):errs.append("UNKNOWN_RULE_ID")
    if re.search(r"REG_|B2B-RULE-|lf_ops|libertad.financiera",text,re.I):errs.append("SKILL_L3_CONTAMINATION")
    normalized=lambda s:re.findall(r"\w+",s.lower())
    tokens=normalized(text)
    grams={tuple(tokens[i:i+8]) for i in range(max(0,len(tokens)-7))}
    for rule in catalog["rules"]:
        words=normalized(rule["rule"])
        if any(tuple(words[i:i+8]) in grams for i in range(max(0,len(words)-7))):
            errs.append("SKILL_RULE_TEXT_DUPLICATED");break
    return sorted(set(errs))
def inspect_repository(root):
    root=Path(root)
    evidence={}
    pom=root/"backend/pom.xml"
    if pom.is_file():
        source=pom.read_text(encoding="utf-8")
        evidence["spring_boot"]="spring-boot" in source
        evidence["flyway"]="flyway" in source.lower()
    pkg=root/"frontend/package.json"
    if pkg.is_file():
        raw=load_json(pkg)
        evidence["next"]="next" in {**raw.get("dependencies",{}),**raw.get("devDependencies",{})}
    evidence["migration"]=bool(list(root.glob("**/V[0-9]*__*.sql")))
    return evidence

def select(evidence,active):
    if not active:raise ValueError("STACK_UNRECOGNIZED: REQUIRES_DECISION: missing active domains")
    hits=[]
    if evidence.get("spring_boot"):hits.append("spring-boot")
    if evidence.get("next"):hits.append("nextjs")
    if bool(evidence.get("flyway")) != bool(evidence.get("migration")):
        raise ValueError("STACK_UNRECOGNIZED: REQUIRES_DECISION: Flyway declaration and migration evidence incomplete")
    if evidence.get("flyway") and evidence.get("migration"):hits.append("postgres-flyway")
    if not hits:raise ValueError("STACK_UNRECOGNIZED: REQUIRES_DECISION")
    return hits
def assemble(pin,selected,active):
    catalog_bytes=(STD/"catalog.json").read_bytes();catalog=json.loads(catalog_bytes)
    actual=digest(catalog_bytes)
    if actual!=pin["catalog_sha256"]:raise ValueError("PIN_DIGEST_MISMATCH")
    skill_data=[];text_sections=[];ids=set();pending=[]
    for slug in selected:
        obj=load_json(DIR/slug/"skill.json")
        if obj["catalog_compat"]!=".".join(pin["catalog_version"].split(".")[:2]):
            raise ValueError("BLOCK_SKILL_CATALOG_PIN_MISMATCH")
        if obj["glossary_compat"]!=".".join(load_json(STD/"glossary/base.json")["glossary_version"].split(".")[:2]):
            raise ValueError("BLOCK_SKILL_GLOSSARY_PIN_MISMATCH")
        proc=(DIR/slug/"SKILL.md").read_text(encoding="utf-8")
        applicable=set(obj["domains"]) & set(active)
        excluded={x["rule_id"] for x in obj["exclude_rule_ids"]}
        for r in catalog["rules"]:
            if r["domain"] in applicable and r["id"] not in excluded:ids.add(r["id"])
        skill_data.append({"skill":slug,"skill_json_sha256":digest((DIR/slug/"skill.json").read_bytes()),"skill_md_sha256":digest(proc.encode())})
        text_sections.append(proc)
    selected_rules=[r for r in catalog["rules"] if r["id"] in ids]
    for r in selected_rules:
        if r.get("status") in ("PENDIENTE_REVISION","VALIDAR_CON_LEGAL"):pending.append(r["id"])
        title=f"{r['id']} [{r.get('status','')}]" + (" (pendiente, no obligatoria)" if r["id"] in pending else "")
        detail=r["rule"]
        if r.get("examples"):
            detail+="\n"+"".join("✅ "+x+"\n" for x in r["examples"]["good"])+"".join("❌ "+x+"\n" for x in r["examples"]["bad"])
        text_sections.append(title+"\n"+detail)
    content="\n\n".join(text_sections)+"\n"
    receipt={"bytes":len(content.encode()),"approx_tokens":(len(content)+3)//4,"catalog_sha256":actual,
       "glossary_sha256":digest((STD/"glossary/base.json").read_bytes()),"skills":skill_data,
       "rule_ids":[x["id"] for x in selected_rules],"pending_rule_ids":pending,
       "assembled_sha256":digest(content.encode()),"warnings":[]}
    if receipt["approx_tokens"]>3000:receipt["warnings"].append("CONTEXT_SIZE_WARNING")
    return content,receipt
def main():
    p=argparse.ArgumentParser();sp=p.add_subparsers(dest="cmd",required=True)
    sp.add_parser("validate")
    s=sp.add_parser("select");s.add_argument("--evidence");s.add_argument("--repo");s.add_argument("--domains",required=True)
    a=sp.add_parser("assemble");a.add_argument("--pin",required=True);a.add_argument("--skills",default="spring-boot");a.add_argument("--domains",default="STD-BE,STD-API,STD-SEC,STD-GEN");a.add_argument("--out",required=True)
    q=p.parse_args();catalog=load_json(STD/"catalog.json");checks=load_json(DIR/"checks/stack-checks.json")
    if q.cmd=="validate":
        errors=[]
        covered=set().union(*(set(load_json(DIR/slug/"skill.json")["domains"]) for slug in SLUGS))
        for domain in (d["id"] for d in catalog["domains"]):
            if domain not in covered and domain not in EXCLUDED_V1_DOMAINS:errors.append("UNCOVERED_DOMAIN")
        for slug in SLUGS:
            obj=load_json(DIR/slug/"skill.json")
            errors+=violations(obj,(DIR/slug/"SKILL.md").read_text(encoding="utf-8"),catalog,checks)
        print(json.dumps({"findings":sorted(set(errors))}));return int(bool(errors))
    if q.cmd=="select":
        try:out=select(inspect_repository(q.repo) if q.repo else load_json(Path(q.evidence)),q.domains.split(","))
        except ValueError as e:print(json.dumps({"error":str(e)}));return 1
        print(json.dumps({"skills":out}));return 0
    try:content,receipt=assemble(load_json(Path(q.pin)),q.skills.split(","),q.domains.split(","))
    except (ValueError,KeyError) as e:print(json.dumps({"error":str(e)}));return 1
    out=Path(q.out);out.parent.mkdir(parents=True,exist_ok=True);out.write_text(content,encoding="utf-8")
    out.with_suffix(".receipt.json").write_text(json.dumps(receipt,indent=2)+"\n",encoding="utf-8")
    print(json.dumps(receipt));return 0
if __name__=="__main__":sys.exit(main())
