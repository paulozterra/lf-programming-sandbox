"""Security regression: all user-supplied PG00 release assertions fail closed."""
from pg02_pg00_bridge_v1 import classify_with_pg00
from pg02_classifier_v1 import PG02Blocked

decision_rows=[{"adr":f"ADR-PROG-STD-{i:03}","estado":"vigente"} for i in range(1,18)]
for release in [None,{},{"state":"PG00_RELEASED"},
    {"state":"PG00_RELEASED","release_ref":"train://self-asserted",
     "release_sha256":"a"*64,"mapping":{"state":"SOURCE_ONLY_CANDIDATE",
     "source_ref":"fixture://unsigned","version":"v1","front_kind_domains":{}}}]:
    try:
        classify_with_pg00({},decision_rows,release,expected_release_sha256="a"*64)
    except PG02Blocked as exc:
        assert str(exc)=="PG00_AUTHORITATIVE_TRANSVERSAL_READER_UNAVAILABLE"
    else:
        raise AssertionError("SELF_ATTESTATION_BYPASS")
print("PG02_PG00_AUTHORITY_BOUNDARY_PASS negatives=4 caller_release_never_authorizes=True")
