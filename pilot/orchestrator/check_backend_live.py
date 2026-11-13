"""Launch isolated Spring app and compare declared methods against live springdoc."""
from __future__ import annotations

import argparse
from pathlib import Path
import subprocess
import time

from contract_validate import compare_runtime, load, ContractBlocked, operations_for_runtime
from urllib.request import urlopen
import json


def run(contract: Path | None = None, *, port: int = 18765):
    proc = subprocess.Popen([
        "mvn", "-B", "-q", "-f", "apps/time-service/pom.xml",
        "spring-boot:run", f"-Dspring-boot.run.arguments=--server.port={port}",
    ], stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True)
    try:
        for attempt in range(45):
            if proc.poll() is not None:
                raise ContractBlocked("T2_BACKEND_PROCESS_EXITED")
            try:
                with urlopen(f"http://127.0.0.1:{port}/v3/api-docs", timeout=8) as reply:
                    runtime = json.load(reply)
                if not isinstance(runtime, dict) or not str(runtime.get("openapi", "")).startswith("3."):
                    raise ContractBlocked("T2_BACKEND_OPENAPI_INVALID")
                sources = [contract] if contract else sorted(Path("contracts").glob("*.openapi.yaml"))
                for source in sources:
                    compare_runtime(load(source), f"http://127.0.0.1:{port}")
                return {"status": "PASS", "contracts": len(sources)}
            except ContractBlocked as exc:
                if "UNAVAILABLE" not in str(exc):
                    raise
                time.sleep(2)
        raise ContractBlocked("T2_BACKEND_RUNTIME_TIMEOUT")
    finally:
        proc.terminate()
        try:
            proc.communicate(timeout=8)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.communicate(timeout=8)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--contract", type=Path)
    args = parser.parse_args()
    print(run(args.contract))
