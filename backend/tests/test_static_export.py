"""The static GitHub Pages fixtures must be exactly what the live API serves."""

import json
import sys
from pathlib import Path

import pytest

from app.demo import SCENARIOS, list_scenarios, run_scenario
from app.models import DemoResponse, ScenarioInfo
from app.reporting import render_json, render_markdown

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
from export_static_demo import export  # noqa: E402


@pytest.fixture(scope="module")
def out(tmp_path_factory):
    path = tmp_path_factory.mktemp("demo-data")
    export(path)
    return path


def test_all_scenarios_and_reports_are_exported(out):
    names = {p.name for p in out.iterdir()}
    assert {"manifest.json", "scenarios.json"} <= names
    for sc in SCENARIOS:
        assert {f"{sc.id}.json", f"{sc.id}.report.md", f"{sc.id}.report.json"} <= names
    assert len(SCENARIOS) == 7


def test_fixtures_validate_against_the_api_models_and_match_the_engine(out):
    listing = json.loads((out / "scenarios.json").read_text())
    assert [ScenarioInfo.model_validate(i) for i in listing] == list_scenarios()
    for sc in SCENARIOS:
        fixture = DemoResponse.model_validate_json((out / f"{sc.id}.json").read_text())
        assert fixture == run_scenario(sc.id)
        assert (out / f"{sc.id}.report.md").read_text() == render_markdown(fixture.analysis)
        assert (out / f"{sc.id}.report.json").read_text() == render_json(fixture.analysis)


def test_manifest_reports_the_engine_version(out):
    from app import __version__

    manifest = json.loads((out / "manifest.json").read_text())
    assert manifest["version"] == __version__ and len(manifest["scenarios"]) == 7


def test_export_is_deterministic(out, tmp_path):
    export(tmp_path)
    for p in out.iterdir():
        assert (tmp_path / p.name).read_bytes() == p.read_bytes(), p.name
