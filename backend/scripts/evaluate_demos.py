#!/usr/bin/env python3
"""Evaluate every demo scenario against its documented expected outcome. Exit code 1 on any failure."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.demo import SCENARIOS, evaluate, run_scenario  # noqa: E402


def main() -> int:
    failed = 0
    for sc in SCENARIOS:
        result = run_scenario(sc.id).analysis
        problems = evaluate(sc.expected, result)
        top = result.hypotheses[0].category if result.hypotheses else "-"
        print(f"{'PASS' if not problems else 'FAIL'}  {sc.id:34s} verdict={result.verdict:19s} top={top}")
        for p in problems:
            print(f"      - {p}")
        failed += bool(problems)
    print(f"\n{len(SCENARIOS) - failed}/{len(SCENARIOS)} scenarios matched their expected outcome")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
