"""Probe an existing QEMU recovery alias in a fresh E2B sandbox, then delete it."""

import argparse
import asyncio
import json
import os

from e2b import AsyncSandbox

from harbor.environments.e2b_qemu_recovery import ALIASES, PROBE_COMMAND, recovery_alias


async def probe(task, alias):
    sandbox = await AsyncSandbox.create(
        template=alias,
        timeout=120,
        metadata={"purpose": "qemu-environment-probe", "task": task},
    )
    try:
        result = await sandbox.commands.run(PROBE_COMMAND, timeout=30)
        return {
            "task": task,
            "alias": alias,
            "sandbox_id": sandbox.sandbox_id,
            "exit_code": result.exit_code,
            "stdout": result.stdout,
            "stderr": result.stderr,
        }
    finally:
        await sandbox.kill()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--task", required=True, choices=sorted(ALIASES))
    args = parser.parse_args()
    if not os.environ.get("E2B_API_KEY") and os.environ.get("e2bapi"):
        os.environ["E2B_API_KEY"] = os.environ["e2bapi"]
    if not os.environ.get("E2B_API_KEY"):
        parser.error("Export E2B_API_KEY or e2bapi")
    result = asyncio.run(probe(args.task, recovery_alias(args.task)))
    print(json.dumps(result, indent=2))
    if result["exit_code"]:
        raise SystemExit(result["exit_code"])


if __name__ == "__main__":
    main()
