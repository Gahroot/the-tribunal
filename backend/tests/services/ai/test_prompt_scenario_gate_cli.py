"""CI reports the complete suite and fails closed without real API calls."""

import json
from unittest.mock import AsyncMock, patch

import pytest

from app.services.ai.prompt_scenario_suite import SCENARIOS, SimulationVerdict
from scripts.dev.prompt_scenario_gate import main


@pytest.mark.asyncio
async def test_gate_reports_every_snapshot_and_failure(tmp_path, capsys):
    paths = []
    for index in range(2):
        path = tmp_path / f"prompt-{index}.json"
        path.write_text(json.dumps({"system_prompt": "Respect consent"}))
        paths.append(str(path))
    verdicts = [
        SimulationVerdict(s.name, i != 0, "rubric reason", 0.5 if i == 0 else 1.0)
        for i, s in enumerate(SCENARIOS)
    ]
    with patch(
        "scripts.dev.prompt_scenario_gate.run_scenarios", AsyncMock(return_value=verdicts)
    ) as run:
        assert await main(paths) == 1
    assert run.await_count == 2
    output = capsys.readouterr().out
    assert output.count("FAIL") == 2
    assert output.count("PASS") == 14
    assert "rubric reason" in output


@pytest.mark.asyncio
async def test_gate_accepts_complete_passing_suite(tmp_path):
    path = tmp_path / "prompt.json"
    path.write_text(json.dumps({"system_prompt": "Respect consent"}))
    verdicts = [SimulationVerdict(s.name, True, "passed", 0.9) for s in SCENARIOS]
    with patch("scripts.dev.prompt_scenario_gate.run_scenarios", AsyncMock(return_value=verdicts)):
        assert await main([str(path)]) == 0


@pytest.mark.asyncio
async def test_gate_rejects_empty_input():
    assert await main([]) == 1
