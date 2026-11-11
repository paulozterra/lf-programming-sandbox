"""PG-03_C4: preserve explicit upstream reuse decision and reject rebuilding."""
import copy
from pg03_strategy_v1 import prepare_strategy
from pg03_reuse_binding_v1 import validate_reuse
from pg03_strategy_v1 import StrategyBlocked
from test_pg03_strategy_v1 import kw
strategy=prepare_strategy(**kw)
upstream=[{"ref":"existing-module","decision":"REUSE_AS_IS"}]
binding=[{"ref":"existing-module","component":"service.module","action":"REUSE_AS_IS"}]
args=dict(strategy=strategy,upstream_reuse=upstream,technical_bindings=binding)
out=validate_reuse(**args)
assert out==validate_reuse(**copy.deepcopy(args)) and not out["handoff_allowed"]
def deny(field,value,code):
    x=copy.deepcopy(args);x[field]=value
    try:validate_reuse(**x)
    except StrategyBlocked as exc:assert str(exc)==code,(str(exc),code)
    else:raise AssertionError(code)
deny("technical_bindings",[{"ref":"existing-module","component":"new.module","action":"EXTEND_EXISTING"}],"REUSE_AS_IS_REDEFINITION_FORBIDDEN")
deny("technical_bindings",[],"REUSE_BINDING_COVERAGE_MISMATCH")
deny("upstream_reuse",[],"UPSTREAM_REUSE_ABSENT")
deny("upstream_reuse",[{"ref":"other","decision":"REUSE_AS_IS"}],"STRATEGY_REUSE_PARITY_MISMATCH")
deny("upstream_reuse",upstream+upstream,"UPSTREAM_REUSE_INVALID")
deny("strategy",{"status":"PASS"},"STRATEGY_NOT_CANDIDATE")
print("PG03_C4_REUSE_PARITY_PASS positive=1 deterministic=1 negatives=6 authority=0")
