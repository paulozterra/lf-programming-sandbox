"""Strict, local-only, data-driven multi-skill resolver. Never infers stack from role or AI."""
import copy,hashlib,json,re
from pathlib import Path
ROOT=Path(__file__).resolve().parent
ROLES=ROOT.parent
class StackBlocked(ValueError):pass
def block(code):raise StackBlocked(code)
def sha_bytes(raw):return hashlib.sha256(raw).hexdigest()
def sha_text(s):return sha_bytes(s.encode("utf-8"))
def stable_sha(obj):return sha_text(json.dumps(obj,ensure_ascii=True,sort_keys=True,separators=(",",":")))
def load_json(name):return json.loads((ROOT/name).read_text(encoding="utf-8"))
def literal(s):
    if not isinstance(s,str) or not s or len(s)>160:block("SKILL_BINDING_INPUT_INVALID")
    return "'"+s.replace("'","''")+"'"
def skill_catalog():
    rows=load_json("skill_catalog_exp.json")["skills"]
    if len({(r["skill_code"],r["version"]) for r in rows})!=len(rows):block("SKILL_CATALOG_DUPLICATE")
    return {(r["skill_code"],r["version"]):r for r in rows}
def skill_material(code,version=None):
    catalog=skill_catalog()
    versions=[v for c,v in catalog if c==code]
    if version is None:
        if len(versions)!=1:block("SKILL_VERSION_REQUIRED")
        version=versions[0]
    entry=catalog.get((code,version))
    if entry is None:block("SKILL_VERSION_MISMATCH" if versions else "SKILL_CODE_NOT_IN_CATALOG")
    path=(ROOT/entry["path"]).resolve()
    rules_path=(ROOT/entry["rules_path"]).resolve()
    if not path.is_relative_to(ROOT.resolve()) or not rules_path.is_relative_to(ROOT.resolve()):
        block("SKILL_PATH_TRAVERSAL")
    raw=path.read_bytes();skill=raw.decode("utf-8")
    if (not skill.startswith("# ") or "CANDIDATE_SANDBOX_ONLY" not in skill or
        "**Área declarada:** "+entry["area"] not in skill or
        "**Código:** "+code not in skill or
        "**Versión:** "+version not in skill):
        block("SKILL_SOURCE_INVALID")
    rules=json.loads(rules_path.read_text(encoding="utf-8"))
    if (rules.get("skill_code")!=code or rules.get("version")!=version or
        rules.get("area")!=entry["area"] or rules.get("standard_family")!=entry["standard_family"]):
        block("SKILL_RULES_METADATA_INVALID")
    checks=rules.get("rules")
    if not isinstance(checks,list) or len(checks)<3 or len({x.get("rule_id") for x in checks})!=len(checks):
        block("SKILL_EXPERT_RULES_INCOMPLETE")
    for r in checks:
        if not isinstance(r.get("text"),str) or not r["text"].strip() or not r.get("source_url","").startswith("https://"):
            block("SKILL_RULE_SOURCE_INVALID")
        if "**"+r["rule_id"]+":** "+r["text"] not in skill or r["source_url"] not in skill:
            block("SKILL_RULE_SOURCE_DRIFT")
    return {"skill_code":code,"skill_version":version,"area":entry["area"],
            "skill_sha256":sha_bytes(raw),"skill_text":skill,
            "source_path":entry["path"],"standard_family":entry["standard_family"],
            "expert_rules":copy.deepcopy(checks)}
def role_material(profile_code):
    slugs={"PERFIL-PROG-BACKEND-EXP":"prog_backend_exp",
           "PERFIL-PROG-FRONTEND-EXP":"prog_frontend_exp",
           "PERFIL-PROG-DATA-EXP":"prog_data_exp"}
    slug=slugs.get(profile_code)
    if not slug:block("PROFILE_ROLE_UNKNOWN")
    path=ROLES/slug/"SKILL.md";raw=path.read_bytes()
    binding=json.loads((ROLES/slug/"contracts/runtime_binding.json").read_text())
    if binding.get("runtime_enabled") is not False or binding.get("promotion_allowed") is not False:
        block("ROLE_RUNTIME_ENABLED")
    if binding["profile_code"]!=profile_code:block("ROLE_CODE_MISMATCH")
    return {"profile_code":profile_code,"area":binding["area"],"profile_sha256":sha_bytes(raw),
            "role_text":raw.decode("utf-8"),"source_path":slug+"/SKILL.md"}
def pg00_source_status(code):
    """Read only immutable, SHA-256-checked normative text from the sandbox snapshot.

    Content is the exact Git blob of the pinned external catalog. No network,
    live Supabase, synthetic standards, or production admission.
    """
    src=load_json("pg00_catalog_sources_exp.json")
    rows=src.get("families",[])
    row=next((r for r in rows if r.get("code")==code),None)
    if not row:block("PG00_STD_FAMILY_UNKNOWN")
    if (src.get("source_repository")!="paulozterra/lf-programming-sandbox"
        or src.get("source_commit_sha")!="f18b2d96b7e1a8263749d35a7afcc9c043521cb8"
        or src.get("source_path")!="standards/catalog.json"
        or src.get("source_sha256")!="26ca9cf9936ef01b50f9af504e4a9b796ee7d7d538d5724ff388c9fb90e8ddb3"
        or src.get("catalog_version")!="0.6.1"
        or src.get("production_authority") is not False
        or src.get("promotion_allowed") is not False):
        block("PG00_STANDARD_SOURCE_PIN_INVALID")
    snapshot=ROOT/"pg00_normative_catalog_snapshot.json"
    if snapshot.is_symlink() or not snapshot.is_file():
        block("PG00_STANDARD_TEXT_UNAVAILABLE")
    raw=snapshot.read_bytes()
    if sha_bytes(raw)!=src["source_sha256"]:
        block("PG00_STANDARD_SOURCE_SHA256_DRIFT")
    try:
        catalog=json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError,ValueError):
        block("PG00_STANDARD_SOURCE_INVALID")
    if (catalog.get("schema_version")!="LF_STANDARDS_CATALOG_V1"
        or catalog.get("catalog_version")!=src["catalog_version"]
        or catalog.get("status")!=src["catalog_status"]
        or not isinstance(catalog.get("rules"),list)):
        block("PG00_STANDARD_SOURCE_INVALID")
    rules=[r for r in catalog["rules"] if r.get("domain")==code]
    if (not rules or len({r.get("id") for r in rules})!=len(rules)
        or any(not isinstance(r.get("rule"),str) or not r["rule"].strip()
               or not isinstance(r.get("id"),str) for r in rules)):
        block("PG00_STANDARD_TEXT_UNAVAILABLE")
    return {"standard_family":code,"standard_source_ref":src["source_ref"],
            "source_sha256":src["source_sha256"],
            "catalog_version":src["catalog_version"],
            "catalog_status":catalog["status"],
            "normative_text_available":True,
            "qualification_only":True,
            "production_authority":False,
            "rules":[{"id":r["id"],"text":r["rule"],
                      "severity":r.get("severity"),
                      "status":r.get("status")}
                     for r in rules]}
def seed_local_binding_table(dsn,run_psql):
    """ONLY call after existing localhost/disposable DB guard."""
    for r in load_json("project_stack_binding_fixtures.json")["rows"]:
        m=skill_material(r["skill_code"],r["skill_version"])
        if m["area"]!=r["area"]:block("SKILL_AREA_MISMATCH")
        cols=["project_ref","area","skill_code","skill_version","skill_sha256","priority"]
        values=[literal(r[k]) for k in cols[:4]]+[literal(m["skill_sha256"]),str(r["priority"])]
        run_psql(dsn,sql="INSERT INTO public.project_stack_binding_exp("+",".join(cols)+") VALUES ("+",".join(values)+")")
def select_binding(project_ref,area,read_row):
    if area not in ("BACKEND","FRONTEND","DATA"):block("SKILL_AREA_INVALID")
    rows=read_row(project_ref,area)
    if not isinstance(rows,list) or not rows:block("SKILL_NOT_BOUND")
    required={"project_ref","area","skill_code","skill_version","skill_sha256","priority"}
    priorities=[];items=[]
    for row in rows:
        if not isinstance(row,dict) or set(row)!=required or row["project_ref"]!=project_ref or row["area"]!=area:
            block("SKILL_BINDING_ROW_INVALID")
        if not isinstance(row["priority"],int) or isinstance(row["priority"],bool) or row["priority"]<=0:
            block("SKILL_PRIORITY_REQUIRED")
        priorities.append(row["priority"])
        material=skill_material(row["skill_code"],row["skill_version"])
        if material["area"]!=area:block("SKILL_AREA_MISMATCH")
        if row["skill_sha256"]!=material["skill_sha256"]:block("SKILL_SHA256_MISMATCH")
        items.append({**material,"project_ref":project_ref,"priority":row["priority"],
                      "binding_row":copy.deepcopy(row),"pg00":pg00_source_status(material["standard_family"])})
    if len(set(priorities))!=len(priorities):block("SKILL_PRIORITY_CONFLICT")
    items.sort(key=lambda x:x["priority"])
    if len({(x["skill_code"],x["skill_version"]) for x in items})!=len(items):
        block("SKILL_BINDING_DUPLICATED")
    primary=items[0]
    identities=[{"skill_code":x["skill_code"],"skill_version":x["skill_version"],
                 "skill_sha256":x["skill_sha256"],"priority":x["priority"]} for x in items]
    return {**primary,"skills":items,"binding_rows":[x["binding_row"] for x in items],
            "skill_set_sha256":stable_sha(identities)}
def read_sql_binding(dsn,run_psql,project_ref,area):
    def read(project,ar):
        sql="SELECT coalesce(jsonb_agg(to_jsonb(b) ORDER BY b.priority NULLS LAST,b.skill_code),'[]'::jsonb)::text FROM public.project_stack_binding_exp b WHERE project_ref="+literal(project)+" AND area="+literal(ar)
        return json.loads(run_psql(dsn,sql=sql))
    return select_binding(project_ref,area,read)
def validate_visible_skill_rules(worker_spec,skill):
    """Deterministic minimum-three source-bound rule gate for each project skill."""
    visible=worker_spec.get("functional_contract",{}).get("role_and_stack",{})
    shown=visible.get("skills",[])
    src=skill.get("skills",[])
    if len(shown)!=len(src):block("WORKER_SKILLS_INCOMPLETE")
    for a,b in zip(src,shown):
        rules=b.get("expert_rules",[])
        if not isinstance(rules,list) or len(rules)<3 or len({r.get("rule_id") for r in rules})<3:
            block("WORKER_SKILL_RULES_TOO_FEW")
        if any(not any(r==r0 for r0 in a["expert_rules"]) for r in rules):
            block("WORKER_SKILL_RULE_SOURCE_MISMATCH")
        if (b.get("skill_code")!=a["skill_code"] or
            b.get("skill_version")!=a["skill_version"] or
            b.get("priority")!=a["priority"] or
            b.get("skill_sha256")!=a["skill_sha256"]):
            block("WORKER_SKILL_IDENTITY_MISMATCH")
    return True

def compose_visible_worker_spec(spec,assignment,role,skill):
    if (assignment.get("profile_code")!=role["profile_code"] or
        assignment.get("area")!=role["area"] or
        assignment.get("project_ref")!=skill["project_ref"] or skill["area"]!=role["area"]):
        block("ROLE_SKILL_ASSIGNMENT_MISMATCH")
    if sha_text(role["role_text"])!=role["profile_sha256"]:block("PROFILE_SHA256_MISMATCH")
    entries=skill.get("skills",[])
    if not entries or skill["skill_set_sha256"]!=stable_sha([
        {"skill_code":x["skill_code"],"skill_version":x["skill_version"],
         "skill_sha256":x["skill_sha256"],"priority":x["priority"]} for x in entries
    ]):block("SKILL_SET_SHA256_MISMATCH")
    rules=[]
    skill_rows=[]
    for item in entries:
        fresh=skill_material(item["skill_code"],item["skill_version"])
        if (item["area"]!=role["area"] or fresh["skill_sha256"]!=item["skill_sha256"] or
            sha_text(item["skill_text"])!=item["skill_sha256"]):
            block("SKILL_SHA256_MISMATCH")
        approved=copy.deepcopy(item["expert_rules"][:3])
        if len(approved)<3:block("SKILL_EXPERT_RULES_INCOMPLETE")
        skill_rows.append({"skill_code":item["skill_code"],"skill_version":item["skill_version"],
                           "skill_sha256":item["skill_sha256"],"priority":item["priority"],
                           "skill_rules":item["skill_text"],"expert_rules":approved,
                           "pg00_standard_source":item["pg00"]})
        rules+=approved
    result=copy.deepcopy(spec)
    if not isinstance(result.get("functional_contract"),dict):block("WORKER_CONTRACT_INVALID")
    result["functional_contract"]["role_and_stack"]={
        "profile_code":role["profile_code"],"profile_sha256":role["profile_sha256"],
        "profile_rules":role["role_text"],"project_ref":skill["project_ref"],
        "area":role["area"],"skill_set_sha256":skill["skill_set_sha256"],
        "skill_code":skill["skill_code"],"skill_version":skill["skill_version"],
        "skill_sha256":skill["skill_sha256"],"skill_rules":skill["skill_text"],
        "skills":skill_rows,"expert_rule_count":len(rules)}
    validate_visible_skill_rules(result,skill)
    return result
