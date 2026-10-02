"""Offline analysis of explicitly selected immutable experiment JSONL files."""

import argparse
from collections.abc import Sequence
from pathlib import Path

from coderepair.experiment_analysis import (
    analyze_experiments,
    stable_json,
    write_analysis,
)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    for version in ("dev-v1", "dev-v2", "dev-v3"):
        parser.add_argument(f"--{version}", type=Path)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args(argv)
    if not any((args.dev_v1, args.dev_v2, args.dev_v3)):
        parser.error(
            "at least one explicit --dev-v1/--dev-v2/--dev-v3 input is required"
        )
    if args.output_dir.exists() or args.output_dir.is_symlink():
        parser.error("output directory already exists; refusing to overwrite")
    try:
        summary = analyze_experiments(
            dev_v1=args.dev_v1, dev_v2=args.dev_v2, dev_v3=args.dev_v3
        )
        write_analysis(summary, args.output_dir)
    except (ValueError, OSError) as error:
        # Do not render a scientific report or expose host paths on failed validation.
        reason = (
            str(error)
            if isinstance(error, ValueError)
            else "could not read inputs or create outputs"
        )
        print(
            stable_json(
                {"validation": {"valid": False, "errors": [reason], "warnings": []}}
            ),
            end="",
        )
        return 1
    print("Analysis validated; summary.json, report.md and attempts.csv written.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
