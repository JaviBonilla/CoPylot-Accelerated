#!/usr/bin/env python3
"""Render tables from the archived annual measurements without running a campaign."""
import argparse
import json
from pathlib import Path

RESULTS = Path(__file__).resolve().parent / "results"


def render():
    matrix = json.loads((RESULTS / "annual-benchmark-matrix.json").read_text())
    validation = json.loads((RESULTS / "annual-benchmark-validation.json").read_text())
    if not matrix["passed"] or not validation["passed"] or len(matrix["rows"]) != 8:
        raise ValueError("Expected eight validated annual measurements")

    lines = [
        "# Archived annual optical benchmarks",
        "",
        "Each row describes a complete measured workload. Displayed values are rounded.",
        "",
        "| Case | Mode | Daylight states | Total wall (s) | Evaluation states/s | Total wall states/s |",
        "| --- | --- | ---: | ---: | ---: | ---: |",
    ]
    for row in matrix["rows"]:
        lines.append(
            f"| {row['case']} | {row['execution_mode']} | {row['evaluated_daylight_states']} | "
            f"{row['total_wall_s']:.6f} | {row['evaluation_states_per_s']:.6f} | "
            f"{row['total_wall_states_per_s']:.6f} |"
        )

    lines.extend([
        "",
        "## Speedups from unrounded total wall times",
        "",
        "| Ratio | CESA-I | Commercial |",
        "| --- | ---: | ---: |",
    ])
    cesa = matrix["speedups_by_case"]["cesa"]["total_wall"]
    commercial = matrix["speedups_by_case"]["commercial"]["total_wall"]
    for ratio, value in cesa.items():
        lines.append(f"| {ratio} | {value:.6f}× | {commercial[ratio]:.6f}× |")
    return "\n".join(lines) + "\n"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, help="Write a new Markdown file instead of stdout")
    args = parser.parse_args()
    report = render()
    if args.output is None:
        print(report, end="")
    else:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with args.output.open("x") as stream:
            stream.write(report)


if __name__ == "__main__":
    main()
