#!/usr/bin/env python3
"""CP1.5 T2 entrypoint: contract-first A9 planning, without per-request decisions."""
from __future__ import annotations

import argparse
from pathlib import Path

from pilot.orchestrator.package_to_lots import prepare as prepare_lots


def prepare(root: Path, request_id: str, *, base_head_sha: str) -> dict:
    """T2 is the default for this route; T1 historical replay remains separate."""
    return prepare_lots(root, request_id, base_head_sha=base_head_sha,
                        contract_mode=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("--request-id", required=True)
    parser.add_argument("--base-head-sha", required=True)
    args = parser.parse_args()
    planned = prepare(args.root, args.request_id, base_head_sha=args.base_head_sha)
    print("T2_CONTRACT_LOTS_PLANNED:" + str(len(planned["lots"])))


if __name__ == "__main__":
    main()
