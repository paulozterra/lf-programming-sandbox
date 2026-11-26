import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import request_timeline as rt


def test_stage_and_task_from_branch():
    assert rt.stage_of("lf/native-registration/req652backend2-ba438cc2166a") == "Registro CP3.6"
    assert rt.task_of("lf/native-registration/req652backend2-ba438cc2166a", "req-652") == "req652backend2"
    assert rt.task_of("lf/native-integration/req652contrato1-run-45544411504", "req-652") == "req652contrato1"
    assert rt.task_of("exam/req652frontend3", "req-652") == "req652frontend3"
    assert rt.task_of("lf/evidence/req-652-cac9e23484ed", "req-652") == "(pedido)"
    assert rt.task_of("lf/generated-t7/744668a6ec7e-req-652", "req-652") == "(pedido)"
    assert rt.stage_of("feature/x") is None


def test_duration_format():
    assert rt.dur(240) == "4 min" and rt.dur(3600 * 6 + 51 * 60) == "6h51"
