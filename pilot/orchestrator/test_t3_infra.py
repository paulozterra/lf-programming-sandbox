"""T3: source-neutral INFRA admission and real JDBC/Flyway proposal checks."""
from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
import re
import uuid
import xml.etree.ElementTree as ET

import pytest

from pilot.orchestrator import atomize, infra_lot, infra_validate, plan_lots
from pilot.orchestrator.native_lot_binding import map_profile, real_write_paths
from pilot.orchestrator.test_contract_t2 import scenario

ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.parametrize("kind", ["first", "second"])
def test_a9_screen_with_explicit_dependency_produces_infra_before_backend(tmp_path, kind):
    # Real A9 screen package, no fake HTTP endpoints or data source records.
    _, package = scenario(tmp_path, kind, slug="t3-" + kind)
    package = deepcopy(package)
    package["dependency_requirements"] = ["spring-jdbc"]
    result = atomize.atomize(package, tmp_path, "a" * 40, run="t3-" + kind)
    items = result["atoms"]
    assert [x["area"] for x in items] == ["INFRA", "CONTRATO", "BACKEND", "FRONTEND"]
    infra, contract, backend, frontend = items
    assert infra["paths"] == ["apps/time-service/pom.xml"]
    assert "spring-jdbc" in [x["id"] for x in infra["missing_dependencies"]]
    assert infra["atom_id"] in backend["depends_on"]
    assert contract["atom_id"] in backend["depends_on"]
    assert infra["atom_id"] not in contract["depends_on"]
    assert frontend["depends_on"] == sorted(frontend["depends_on"])
    assert result["simulation_only"] is True


def test_synthetic_random_data_generates_infra_and_classpath_path(tmp_path):
    token = uuid.uuid4().hex[:12]
    module = "module-" + token
    data_path = atomize._route("DATA", module, atomize._rules(), tmp_path)
    assert len(data_path) == 1
    assert re.fullmatch(
        r"apps/time-service/src/main/resources/db/migration/V[0-9]+__module_[a-f0-9]+[.]sql",
        data_path[0])
    data = {"atom_id": "ATOM-" + token, "area": "DATA", "functional_module": module,
            "front_id": "F3-" + token, "requirement_ids": ["REQ-R" + token.upper()],
            "paths": data_path, "depends_on": []}
    infra = infra_lot.infra_atom({}, [data])
    assert infra and infra["area"] == "INFRA"
    allowed = infra_lot.policy()["database"]["config_files"]
    assert infra["paths"] == allowed
    assert {x["id"] for x in infra["missing_dependencies"]} == {
        "spring-jdbc", "spring-flyway", "flyway-postgresql", "postgresql-driver"}
    fixture = {"atoms": [data, infra]}
    planned = [{"id": "SOL-" + token, "area": "DATA",
                "profile_code": "PERFIL-PROG-DATA-EXP",
                "write_paths": data_path, "depends_on": [],
                "requirement_ids": data["requirement_ids"]}]
    data["depends_on"] = [infra["atom_id"]]
    merged = plan_lots._t3_infra_lots({}, fixture, planned)
    assert [x["area"] for x in merged] == ["INFRA", "DATA"]
    assert merged[1]["depends_on"] == [merged[0]["id"]]
    assert merged[1]["infra_context_ref"] == infra["policy_ref"]
    assert merged[0]["profile_code"] == "PERFIL-PROG-BACKEND-SPRING-EXP"


def test_unlisted_or_malformed_dependency_blocks():
    with pytest.raises(infra_lot.DependencyBlocked, match="DEPENDENCIA_NO_PERMITIDA"):
        infra_lot.infra_atom({"dependency_requirements": ["unapproved-library"]},
                             [{"area": "BACKEND", "front_id": "F3-X",
                               "requirement_ids": ["REQ-RANDOM-X"]}])
    with pytest.raises(infra_lot.DependencyBlocked, match="DEPENDENCIA_NO_PERMITIDA"):
        infra_lot.infra_atom({"dependency_requirements": ["spring-jdbc:latest"]},
                             [{"area": "BACKEND", "front_id": "F3-X",
                               "requirement_ids": ["REQ-RANDOM-X"]}])


def test_version_mismatch_blocks_instead_of_upgrading(tmp_path):
    root=tmp_path
    pom=root/"apps/time-service/pom.xml"
    pom.parent.mkdir(parents=True)
    pom.write_text("""<project xmlns="http://maven.apache.org/POM/4.0.0">
      <dependencies><dependency><groupId>org.springframework.boot</groupId>
      <artifactId>spring-boot-starter-jdbc</artifactId>
      <version>99.0.0</version></dependency></dependencies></project>""")
    frontend=root/"frontend/package.json"
    frontend.parent.mkdir()
    frontend.write_text('{"dependencies":{}}')
    atoms=[{"area":"BACKEND","front_id":"F3-ANY",
            "requirement_ids":["REQ-RANDOM-A"]}]
    with pytest.raises(infra_lot.DependencyBlocked,
                       match="DEPENDENCIA_VERSION_NO_PERMITIDA"):
        infra_lot.infra_atom({"dependency_requirements":["spring-jdbc"]},
                             atoms,root=root)


def _constructor_infra_proposal(root):
    """Test-only files: never write the real app's pom or config."""
    policy = infra_lot.policy()
    maven = policy["targets"]["maven"]
    pom = root / maven["manifest"]
    pom.parent.mkdir(parents=True)
    dependencies = "".join(
        "<dependency><groupId>" + entry["group_id"] +
        "</groupId><artifactId>" + entry["artifact_id"] +
        "</artifactId><version>" + entry["version"] +
        "</version></dependency>" for entry in maven["dependencies"]
    )
    pom.write_text('<project xmlns="http://maven.apache.org/POM/4.0.0">'
                   '<dependencies>' + dependencies + '</dependencies></project>')
    npm = root / policy["targets"]["npm"]["manifest"]
    npm.parent.mkdir(parents=True)
    npm.write_text('{"dependencies":{}}')
    db = policy["database"]
    app = root / db["config_files"][1]
    app.parent.mkdir(parents=True, exist_ok=True)
    app.write_text("app.time.zone=UTC\n" +
                   "".join(k + "=" + v + "\n" for k,v in db["properties"].items()))
    env = root / db["config_files"][2]
    env.write_text("".join(k + "=\n" for k in db["env_vars"]))
    return db


def test_constructor_db_proposal_follows_allowlist_and_no_secrets(tmp_path):
    db = _constructor_infra_proposal(tmp_path)
    assert infra_validate.check_infra(tmp_path)
    props = tmp_path / db["config_files"][1]
    props.write_text(props.read_text().replace("${DB_PASSWORD}", "hard-coded-password"))
    with pytest.raises(infra_lot.DependencyBlocked, match="T3_DATABASE_CONFIG_INVALID"):
        infra_validate.check_infra(tmp_path)
    props.write_text("".join(k + "=" + v + "\n" for k,v in db["properties"].items()))
    env = tmp_path / db["config_files"][2]
    env.write_text("DB_URL=jdbc:postgresql://example\nDB_USERNAME=\nDB_PASSWORD=\n")
    with pytest.raises(infra_lot.DependencyBlocked, match="T3_ENV_EXAMPLE_SECRET_OR_MISSING"):
        infra_validate.check_infra(tmp_path)


def test_native_scope_prevents_direct_other_area_config_edits(tmp_path):
    (tmp_path/"apps/time-service").mkdir(parents=True)
    paths = infra_lot.policy()["database"]["config_files"]
    assert real_write_paths(tmp_path,"INFRA",paths) == sorted(paths)
    assert map_profile("PERFIL-PROG-BACKEND-SPRING-EXP","INFRA")["area"] == "BACKEND"
    with pytest.raises(Exception, match="CP34_FAKE_OR_UNSAFE_PATH"):
        real_write_paths(tmp_path,"DATA",["apps/time-service/pom.xml"])
    with pytest.raises(Exception, match="CP34_FAKE_OR_UNSAFE_PATH"):
        real_write_paths(tmp_path,"INFRA",["apps/time-service/src/main/java/Unsafe.java"])
