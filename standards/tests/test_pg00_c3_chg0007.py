"""CHG-0007 narrow source-coverage contract, not release authorization."""
import json
from pathlib import Path
def test_additive_adr_coverage():
    root=Path(__file__).resolve().parents[1]
    d=json.loads((root/"catalog.json").read_text())
    chg=json.loads((root/"changes"/"CHG-0007.json").read_text())
    assert d["catalog_version"]=="0.7.0"
    assert chg["approved_by"] is None
    assert chg["evidence"]["train"]=="NOT_APPLIED"
    r={x["id"]:x for x in d["rules"]}
    assert len(r)==87
    for id,fragment in {
        "STD-MSG-04":"trace_code",
        "STD-IAC-08":"Fase 4",
        "STD-LOG-05":"caché",
        "STD-GEN-08":"APAGADA en V1"
    }.items():
        x=r[id]
        assert fragment in x["rule"],id
        assert isinstance(x["examples"]["good"],list) and isinstance(x["examples"]["bad"],list)
        assert x["examples"]["good"] and x["examples"]["bad"]
        assert x["examples"]["good"]!=x["examples"]["bad"]
        assert x["enforcement"]["state"]=="review"
    assert "REQUIRES_DECISION" in r["STD-MSG-04"]["rule"]
    assert "80 %" in r["STD-GEN-08"]["rule"] and "100 %" in r["STD-GEN-08"]["rule"]
    assert "no desactiva" in r["STD-LOG-05"]["rule"]
