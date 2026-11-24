"""The committed data/demo files must match what the generators produce."""

from pathlib import Path

import pytest

from app.demo import SCENARIOS

DATA = Path(__file__).resolve().parents[2] / "data" / "demo"


@pytest.mark.skipif(not DATA.exists(), reason="data/demo not present")
@pytest.mark.parametrize("scenario", SCENARIOS, ids=lambda s: s.id)
def test_committed_dataset_matches_generator(scenario):
    path = DATA / f"{scenario.id}.{scenario.extension}"
    assert path.exists(), f"run backend/scripts/export_demo_data.py ({path.name} missing)"
    assert path.read_text(encoding="utf-8") == scenario.render()
