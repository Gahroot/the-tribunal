"""CI gate for checked-in prompt snapshots in backend/prompts/."""

import asyncio
import json
import sys
from pathlib import Path
from types import SimpleNamespace

from app.services.ai.prompt_scenario_suite import SCENARIOS, run_scenarios


async def main(paths: list[str]) -> int:
    if not paths:
        print("No prompt snapshots supplied", file=sys.stderr)
        return 1
    failed = False
    for path in paths:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        if (
            not isinstance(data, dict)
            or not isinstance(data.get("system_prompt"), str)
            or not data["system_prompt"].strip()
        ):
            raise ValueError(f"Invalid prompt snapshot: {path}")
        greeting = data.get("initial_greeting")
        if greeting is not None and not isinstance(greeting, str):
            raise ValueError(f"Invalid greeting: {path}")
        verdicts = await run_scenarios(
            SimpleNamespace(system_prompt=data["system_prompt"], initial_greeting=greeting)
        )
        failed |= len(verdicts) != len(SCENARIOS) or any(not v.success for v in verdicts)
        for verdict in verdicts:
            status = "PASS" if verdict.success else "FAIL"
            print(f"{path}: {verdict.name}: {status} ({verdict.score:.2f}) - {verdict.reason}")
    return int(failed)


if __name__ == "__main__":
    sys.exit(asyncio.run(main(sys.argv[1:])))
