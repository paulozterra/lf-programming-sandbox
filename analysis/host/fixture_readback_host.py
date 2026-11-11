"""F1: strictly offline SBX-AUTH-LOGIN readback host, with dual untrusted references.

The supabase:// values are syntactic compatibility identifiers only; no provider
is ever contacted, no source authority/currentness is asserted, and every
file read is bound to fixture://<name>@SHA256 in a separate provenance ledger.
Do not import this host from production workflows.
"""
from __future__ import annotations

from copy import deepcopy
import hashlib
import importlib.util
import json
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[2]
STAGE = PROJECT / "analysis/programming_analysis"
DEFAULT_FIXTURES = PROJECT / "analysis/fixtures/sbx_auth_login"
TARGET = "SBX-AUTH-LOGIN"
FILES = (
    "screen_contract.json", "direct_rules.json", "effective_rules.json",
    "policies.json", "elements.json", "states.json", "variants.json",
    "relations.json", "inventory.json", "ekb.json", "adr.json",
    "decision_asof.json", "semantic_signals.json",
)
SOURCE_PREFIX = "fixture://sbx_auth_login/"
CANONICAL_SCREEN = "supabase://lf_ops.pantallas/" + TARGET


class FixtureBlocked(ValueError):
    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


def block(code):
    raise FixtureBlocked(code)


def load_stage(step: str):
    path = STAGE / "steps" / step / "validators" / "run.py"
    spec = importlib.util.spec_from_file_location("sbx_f1_" + step, path)
    if spec is None or spec.loader is None:
        block("SBX_STAGE_MODULE_MISSING:" + step)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class FixtureHost:
    def __init__(self, root: Path = DEFAULT_FIXTURES):
        self.root = Path(root)
        self.provenance = {}

    def read_all(self):
        pin = self.root / "SOURCE_PIN.json"
        if not pin.is_file():
            block("SBX_SOURCE_PIN_MISSING")
        try:
            manifest = json.loads(pin.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            block("SBX_SOURCE_PIN_INVALID")
        entries = manifest.get("files")
        if (manifest.get("schema_version") != "SBX_FIXTURE_PIN_V1"
                or manifest.get("fixture_id") != TARGET
                or manifest.get("simulation") is not True
                or not isinstance(entries, list)
                or [x.get("file") for x in entries if isinstance(x, dict)] != list(FILES)):
            block("SBX_SOURCE_PIN_INVALID")
        data = {}
        self.provenance = {}
        for entry in entries:
            name = entry["file"]
            path = self.root / name
            if not path.is_file():
                block("SBX_FIXTURE_MISSING:" + name)
            raw = path.read_bytes()
            digest = hashlib.sha256(raw).hexdigest()
            if digest != entry.get("sha256"):
                block("SBX_FIXTURE_SHA256_MISMATCH:" + name)
            try:
                obj = json.loads(raw)
            except (ValueError, UnicodeDecodeError):
                block("SBX_FIXTURE_JSON_INVALID:" + name)
            if not isinstance(obj, dict) or obj.get("imitates") != entry.get("imitates"):
                block("SBX_FIXTURE_SOURCE_IDENTITY_INVALID:" + name)
            data[name] = obj
            self.provenance[name] = SOURCE_PREFIX + name + "@" + digest
        return data

    def source_arguments(self, data):
        screen, direct = data["screen_contract.json"], data["direct_rules.json"]
        effective, policies = data["effective_rules.json"], data["policies.json"]
        if screen.get("target_ref") != TARGET or screen.get("screen_status") != "VIGENTE":
            block("SBX_SCREEN_IDENTITY_INVALID")
        sections = screen.get("contract")
        names = {"fields", "errors", "visual", "context", "metadata",
                 "profiles", "analytics", "evidence", "rules", "policies"}
        if not isinstance(sections, dict) or set(sections) != names:
            block("SBX_SCREEN_CONTRACT_INCOMPLETE")
        # A3's material contract is eight sections, exactly as the fixed producer
        # expects; raw contract rules/policies are separate typed readbacks.
        material = {key: deepcopy(sections[key]) for key in (
            "fields", "errors", "visual", "context",
            "metadata", "profiles", "analytics", "evidence")}
        if (not isinstance(material["fields"], list)
                or not isinstance(material["errors"], list)
                or not isinstance(material["visual"], dict)):
            block("SBX_SCREEN_CONTRACT_INCOMPLETE")
        rows, configs = direct.get("linked_rules"), direct.get("valor_config")
        if not isinstance(rows, list) or not isinstance(configs, list):
            block("SBX_DIRECT_RULES_INCOMPLETE")
        cfg = {item.get("code"): item for item in configs if isinstance(item, dict)}
        if len(cfg) != len(configs):
            block("SBX_DIRECT_RULE_CONFIG_INVALID")
        for row in rows:
            code = row.get("code") if isinstance(row, dict) else None
            if code not in cfg or "valor_config" not in cfg[code]:
                block("SBX_VIGENTE_VALOR_CONFIG_MISSING:" + str(code))
        links = effective.get("rules")
        if not isinstance(links, list) or not links:
            block("SBX_EFFECTIVE_RULES_INCOMPLETE")
        for row in links:
            if not isinstance(row, dict) or "config" not in row:
                block("SBX_EFFECTIVE_VALOR_CONFIG_MISSING")
        if not isinstance(policies.get("policy_links"), list) or not isinstance(policies.get("policy_objects"), list):
            block("SBX_POLICY_BACKUP_MISSING")
        if not isinstance(data["inventory.json"].get("objects"), list):
            block("SBX_INVENTORY_READBACK_INCOMPLETE")
        for name,field in (("elements.json","elements"),("states.json","states"),
                           ("variants.json","variants"),("relations.json","relations"),
                           ("ekb.json","entries"),("adr.json","records")):
            if not isinstance(data[name].get(field), list):
                block("SBX_FIXTURE_REQUIRED_FIELD_MISSING:" + name + ":" + field)
        if data["decision_asof.json"].get("state") not in ("UNKNOWN", "RESOLVED"):
            block("SBX_DECISION_ASOF_INVALID")
        eff_ref = ("supabase://programacion.fn_input_effective_rule_links_v1/"
                   + str(effective["screen_id"]) + "/INPUT_GOVERNANCE")
        policy_objects = deepcopy(policies["policy_objects"])
        backup_refs = [x["source_ref"] for x in policy_objects if x.get("read_origin") == "DIRECT_CANONICAL_POLICY_LOOKUP"]
        return {
            "schema_version": "LF_SCREEN_SOURCE_READBACK_V1",
            "business": "LF", "source_function": "lf_ops.fn_screen_contract_v1",
            "target_ref": TARGET, "screen_ref": CANONICAL_SCREEN,
            "screen_status": screen["screen_status"],
            "contract_version": screen.get("contract_version", ""),
            "contract_sections": material,
            "linked_rules": deepcopy(rows),
            "policy_links": deepcopy(policies["policy_links"]),
            "effective_rule_readback": {
                "screen_id": effective["screen_id"], "business": "LF",
                "target_ref": TARGET, "consumer": "INPUT_GOVERNANCE",
                "source_function": "programacion.fn_input_effective_rule_links_v1",
                "source_ref": eff_ref, "source_attested": False,
                "rules": deepcopy(links),
            },
            "policy_resolution_readback": {
                "schema_version": "LF_SCREEN_POLICIES_READBACK_V1",
                "source_function": "lf_ops.fn_screen_contract_v1",
                "business": "LF", "target_ref": TARGET,
                "source_ref": CANONICAL_SCREEN, "source_attested": False,
                "policy_objects": policy_objects,
                "supplemental_policy_source_refs": backup_refs,
            },
        }

    def run(self, request_text: str):
        data = self.read_all()  # all 13 required sources, without network
        semantic = data["semantic_signals.json"]
        if semantic.get("simulation") is not True or request_text != semantic.get("request_text"):
            block("SBX_SEMANTIC_REQUEST_NOT_PRESTRUCTURED")
        a1_input = deepcopy(semantic.get("a1_structured"))
        a2_input = deepcopy(semantic.get("a2_signals"))
        if not isinstance(a1_input, dict) or not isinstance(a2_input, dict):
            block("SBX_SEMANTIC_SIGNALS_INCOMPLETE")
        if a1_input.get("objective", {}).get("problem_statement") != request_text:
            block("SBX_SEMANTIC_REQUEST_DRIFT")
        # Rebind all external A1/A2 fixture evidence to verified file bytes.
        # No bare fixture path is a trusted source reference.
        semantic_ref = self.provenance["semantic_signals.json"]
        a1_input["request_identity"]["request_ref"] = semantic_ref
        a1_input["source_refs"] = [semantic_ref]
        for fact in a1_input["provided_facts"]:
            fact["source_ref"] = semantic_ref
        a2_input["evidence_refs"] = [semantic_ref]
        # Exact approved model-independent host signal; no prompt interpretation.
        a1 = load_stage("a1").run(a1_input)
        if a1.get("status") != "VALID_OUTPUT":
            block("SBX_A1_BLOCKED:" + ",".join(a1.get("blocking_codes", [])))
        a2 = load_stage("a2").run(a1, a2_input)
        if not isinstance(a2.get("classification"), dict):
            block("SBX_A2_BLOCKED:" + ",".join(a2.get("blocking_codes", [])))
        a3_sources = self.source_arguments(data)
        a3 = load_stage("a3").run({
            "REQUEST_CONTEXT_V1": a1["payload"],
            "ANALYSIS_CHANGE_CLASSIFICATION_V1": a2["classification"],
        }, a3_sources)
        if a3.get("status") == "BLOCKED":
            block("SBX_A3_BLOCKED:" + ",".join(a3.get("blocking_codes", [])))
        inventory = data["inventory.json"]
        a4 = load_stage("a4").run(a3, a2["classification"], {
            "schema_version": "A4_EXISTING_IMPACT_CORE_READBACK_V1",
            "business": "LF", "target_ref": TARGET, "source_attested": False,
            "inventory_object": None, "identity_binding": None,
            "impact_readback": None, "dependency_readback": None,
            "synthetic_inventory_empty": not inventory["objects"],
        })
        if a4.get("status") == "BLOCKED":
            block("SBX_A4_BLOCKED:" + ",".join(a4.get("blocking_codes", [])))
        policy = json.loads((STAGE / "steps/a5/contracts/deterministic_decision_sources_v1.json").read_text())
        a5_sources = {
            "schema_version": "A5_GOVERNED_DECISION_READBACK_V1",
            "business": "LF", "target_ref": TARGET, "source_attested": False,
            "adr_trigger_review": {
                "flags": {key: False for key in policy["material_adr_triggers"]},
                "evidence_ref": a3["source_refs"][0],
                "source_attested": False,
            },
            "asof_resolution": {
                "schema_version": "LF_DECISION_CONTEXT_ASOF_RESOLUTION_V1",
                "state": "UNKNOWN", "subject_ref": TARGET,
            },
            "material_decisions": [],
        }
        a5 = load_stage("a5").run({
            "REQUEST_CONTEXT_V1": a1["payload"],
            "ANALYSIS_CHANGE_CLASSIFICATION_V1": a2["classification"],
            "TARGETED_EVIDENCE_SET_V1": a3,
            "SHARED_CHANGE_IMPACT_ANALYSIS": a4,
        }, a5_sources)
        if a5.get("status") == "BLOCKED":
            block("SBX_A5_BLOCKED:" + ",".join(a5.get("blocking_codes", [])))
        return {
            "simulation": True, "production_authority": False,
            "source_attested": False, "currentness_attested": False,
            "business_binding": "LF_FOR_PRODUCER_COMPATIBILITY_ONLY",
            "target_ref": TARGET, "request_text": request_text,
            "fixture_provenance": deepcopy(self.provenance),
            "canonical_source_identities_are_simulated": True,
            "stages": {"A1": a1, "A2": a2, "A3": a3, "A4": a4, "A5": a5},
        }
