from pathlib import Path
sql=Path(__file__).with_name("pg01_c4_readback_candidate_v1.sql").read_text()
code="\n".join(line for line in sql.splitlines() if not line.lstrip().startswith("--"))
for token in [
 "SECURITY INVOKER","fn_lf_programming_context_handoff_receipt_resolve_v2",
 "PG01_C4_UPSTREAM_NOT_ADMITTED","PG01_C4_CONTEXT_MISMATCH",
 "PG01_C4_FRAMEWORK_PROVENANCE_NOT_IMPLEMENTED",
 "'verified',false","PG01_C4_READBACK_UNDETERMINED",
]:
 assert token in sql,token
for forbidden in ["'verified',true","SECURITY DEFINER","GRANT EXECUTE","INSERT INTO","UPDATE private.","DELETE FROM"]:
 assert forbidden not in code,forbidden
assert sql.count("RETURN jsonb_build_object('verified',false")==4
print("PG01_C4_SQL_FAIL_CLOSED_STATIC_PASS verified_true=0 writes=0 grants=0")
