"""PG-00 / PG-02 authority boundary. No caller-provided release can authorize use."""
from pg02_classifier_v1 import PG02Blocked

EXPECTED_ADRS = tuple(f"ADR-PROG-STD-{i:03}" for i in range(1, 18))

def classify_with_pg00(snapshot, decision_rows, mapping_release, *, expected_release_sha256):
    """Fail closed until an independently authenticated transversal reader is installed.

    Neither caller-supplied ADR rows, a status of PG00_RELEASED, a digest,
    nor a receipt string is evidence of an authorized catalog.
    Do not add a test fixture that turns this path on.
    """
    raise PG02Blocked("PG00_AUTHORITATIVE_TRANSVERSAL_READER_UNAVAILABLE")
