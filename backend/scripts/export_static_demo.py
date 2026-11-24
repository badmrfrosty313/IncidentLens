#!/usr/bin/env python3
"""Generate the fixtures behind the static (GitHub Pages) demonstration build.

    python scripts/export_static_demo.py --out ../frontend/public/demo-data

Every file is produced by the real analysis engine at build time - nothing is hand-written:

    manifest.json           engine name/version, scenario ids
    scenarios.json          what GET /api/demo returns
    <id>.json               what GET /api/demo/<id> returns
    <id>.report.md          what GET /api/demo/<id>/report?format=markdown returns
    <id>.report.json        what GET /api/demo/<id>/report?format=json returns

The output is deterministic (seeded scenarios), so two runs produce identical bytes.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from pydantic import TypeAdapter  # noqa: E402

from app import __version__  # noqa: E402
from app.demo import list_scenarios, run_scenario  # noqa: E402
from app.models import ScenarioInfo  # noqa: E402
from app.reporting import render_json, render_markdown  # noqa: E402


def export(out: Path) -> list[Path]:
    out.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []

    def put(name: str, text: str) -> None:
        path = out / name
        path.write_text(text, encoding="utf-8", newline="\n")
        written.append(path)

    scenarios = list_scenarios()
    put("scenarios.json", TypeAdapter(list[ScenarioInfo]).dump_json(scenarios).decode())
    for info in scenarios:
        demo = run_scenario(info.id)
        put(f"{info.id}.json", demo.model_dump_json())
        put(f"{info.id}.report.md", render_markdown(demo.analysis))
        put(f"{info.id}.report.json", render_json(demo.analysis))
    first = run_scenario(scenarios[0].id).analysis
    manifest = json.dumps(
        {"version": __version__, "engine": first.engine, "engine_version": first.engine_version,
         "scenarios": [s.id for s in scenarios]}
    )
    put("manifest.json", manifest)
    return written


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", type=Path, required=True, help="output directory (created if missing)")
    args = ap.parse_args()
    files = export(args.out)
    print(f"wrote {len(files)} files to {args.out}")


if __name__ == "__main__":
    main()
