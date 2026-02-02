"""IVR testing utilities.

This module provides tools for testing IVR navigation and detection:
- IVRSimulator: Simulates IVR phone menus for testing agents
- ScenarioLoader: Loads IVR scenarios from YAML files
- IVRTestHarness: Runs agents through IVR simulation scenarios
- IVRTestLLMClient: Protocol for LLM clients in testing

Example usage:
    from app.services.ai.testing import IVRSimulator, ScenarioLoader

    scenario = ScenarioLoader.load("path/to/scenario.yaml")
    simulator = IVRSimulator(scenario)

    # Get initial menu
    transcript = simulator.get_current_transcript()

    # Send DTMF and get next menu
    success, response = simulator.send_dtmf("1")

For integration testing with agents:
    from app.services.ai.testing import IVRTestHarness, ScenarioLoader
    from app.services.ai.testing.ivr_test_llm import OpenAITestClient

    client = OpenAITestClient(api_key="sk-...", model="gpt-4o-mini")
    harness = IVRTestHarness(llm_client=client)

    async with async_session() as db:
        agent = await harness.load_agent(db, "My Agent", "My Workspace")
        scenarios = ScenarioLoader.load_directory("tests/scenarios")
        report = await harness.run_scenarios(agent, list(scenarios.values()), "My Workspace")
        print(report.to_markdown())
"""

from app.services.ai.testing.ivr_simulator import (
    IVRMenuOption,
    IVRScenario,
    IVRSimulator,
    IVRState,
)
from app.services.ai.testing.ivr_test_harness import (
    AgentNotFoundError,
    IVRTestConfig,
    IVRTestHarness,
    WorkspaceNotFoundError,
)
from app.services.ai.testing.ivr_test_llm import (
    GrokTestClient,
    IVRTestLLMClient,
    MockLLMClient,
    OpenAITestClient,
)
from app.services.ai.testing.ivr_test_models import (
    IVRTestReport,
    IVRTestResult,
    IVRTestTurn,
)
from app.services.ai.testing.scenario_loader import ScenarioLoader

__all__ = [
    # Simulator
    "IVRMenuOption",
    "IVRScenario",
    "IVRSimulator",
    "IVRState",
    # Scenario loader
    "ScenarioLoader",
    # Test harness
    "AgentNotFoundError",
    "IVRTestConfig",
    "IVRTestHarness",
    "WorkspaceNotFoundError",
    # LLM clients
    "GrokTestClient",
    "IVRTestLLMClient",
    "MockLLMClient",
    "OpenAITestClient",
    # Test models
    "IVRTestReport",
    "IVRTestResult",
    "IVRTestTurn",
]
