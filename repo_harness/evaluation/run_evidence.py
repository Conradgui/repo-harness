"""Release evidence entrypoint."""

from pathlib import Path

from ..release_evidence import run_phase2_scenario_gate


def run(output_dir):
    return run_phase2_scenario_gate(Path(output_dir))

