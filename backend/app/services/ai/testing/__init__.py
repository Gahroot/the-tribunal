"""IVR testing utilities.

This module provides tools for testing IVR navigation and detection:
- IVRSimulator: Simulates IVR phone menus for testing agents
- ScenarioLoader: Loads IVR scenarios from YAML files

Example usage:
    from app.services.ai.testing import IVRSimulator, ScenarioLoader

    scenario = ScenarioLoader.load("path/to/scenario.yaml")
    simulator = IVRSimulator(scenario)

    # Get initial menu
    transcript = simulator.get_current_transcript()

    # Send DTMF and get next menu
    success, response = simulator.send_dtmf("1")
"""

from app.services.ai.testing.ivr_simulator import (
    IVRMenuOption,
    IVRScenario,
    IVRSimulator,
    IVRState,
)
from app.services.ai.testing.scenario_loader import ScenarioLoader

__all__ = [
    "IVRMenuOption",
    "IVRScenario",
    "IVRSimulator",
    "IVRState",
    "ScenarioLoader",
]
