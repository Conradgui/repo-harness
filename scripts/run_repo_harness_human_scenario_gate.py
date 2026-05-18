"""Run RepoHarness human scenario gate evidence."""

import argparse
import json
from pathlib import Path

from repo_harness.release_evidence import run_phase2_scenario_gate


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output",
        default="release/v3-compat-parity",
        help="RepoHarness evidence output directory.",
    )
    args = parser.parse_args()
    payload = run_phase2_scenario_gate(Path(args.output))
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0 if payload.get("status") == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())

