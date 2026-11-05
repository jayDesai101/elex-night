"""The four acceptance gates, read from reports/backtest_metrics.json (make backtest)."""

import json
from pathlib import Path

import pytest

METRICS = Path("reports/backtest_metrics.json")
pytestmark = pytest.mark.slow


@pytest.fixture(scope="module")
def gates() -> dict:
    if not METRICS.exists():
        pytest.fail("run `uv run elex backtest` first")
    return json.loads(METRICS.read_text())["gates"]


@pytest.mark.parametrize(
    "name",
    [
        "gate1_beats_naive_at_50",
        "gate2_not_worse_than_mean_swing_at_50",
        "gate3_coverage",
        "gate4_speed_under_1s",
    ],
)
def test_gate(gates: dict, name: str) -> None:
    assert gates[name]["pass"], f"{name}: {gates[name]['values']}"
