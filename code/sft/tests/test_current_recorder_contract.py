"""Opt-in contract test against a pinned, audit-only Harness checkout.

No model, GPU, benchmark instruction or credentials are used. Production SFT
consumes export files and never imports Harness internals.
"""

import asyncio
import os
import sys
import tempfile
import unittest
from pathlib import Path

from adapters.openharness_v2 import load_rollout


@unittest.skipUnless(
    os.environ.get("TMAX_AUDIT_HARNESS") and sys.version_info >= (3, 12),
    "set explicit audited Harness source path",
)
class CurrentRecorderContract(unittest.TestCase):
    def test_background_flush_artifact_export_and_native_messages(self):
        sys.path.insert(0, os.environ["TMAX_AUDIT_HARNESS"])
        from foundation.rollouts.export import RolloutView, exportDirectories
        from foundation.rollouts.store import Recorder

        async def record(root):
            recorder = await Recorder.create(
                "fixture-session", root, metadata={"task_id": "public-fixture"}
            )
            recorder.append("run_start", run_id="run-1")
            recorder.append(
                "call_start",
                run_id="run-1",
                call_id="call-1",
                model="fixture-model",
                input=[{"role": "user", "content": "Inspect a public fixture."}],
            )
            recorder.append(
                "call_payload",
                run_id="run-1",
                call_id="call-1",
                payload={
                    "messages": [
                        {"role": "system", "content": "Public fixture"},
                        {"role": "user", "content": "Inspect a public fixture."},
                    ],
                    "tools": [],
                },
                fidelity="provider_payload",
            )
            recorder.append(
                "call_end",
                run_id="run-1",
                call_id="call-1",
                status="completed",
                response={
                    "role": "assistant",
                    "stopReason": "toolUse",
                    "content": [
                        {"type": "thinking", "thinking": "Check the file."},
                        {
                            "type": "toolCall",
                            "id": "tool-1",
                            "name": "read",
                            "arguments": {"path": "fixture.txt"},
                        },
                    ],
                },
            )
            recorder.append(
                "tool_start",
                run_id="run-1",
                call_id="call-1",
                execution_id="exec-1",
                tool_call_id="tool-1",
                name="read",
                args={"path": "fixture.txt"},
            )
            recorder.append(
                "tool_raw",
                run_id="run-1",
                call_id="call-1",
                execution_id="exec-1",
                result={"content": "public output " * 10000},
            )
            recorder.append(
                "tool_end",
                run_id="run-1",
                call_id="call-1",
                execution_id="exec-1",
                status="completed",
            )
            recorder.append("run_end", run_id="run-1", status="completed")
            with self.assertRaisesRegex(ValueError, "still being written"):
                RolloutView.open(root)
            await recorder.aclose()
            self.assertTrue(recorder.closed)

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "journal"
            asyncio.run(record(root))
            export = Path(tmp) / "export"
            exportDirectories([root], export)
            for directory in (root, export):
                trajectory = load_rollout(directory, metadata={"reward": 1})
                self.assertEqual(
                    trajectory["status"], "completed", trajectory["metadata"]
                )
                call = trajectory["calls"][0]
                self.assertEqual(call["request_messages"][0]["role"], "system")
                self.assertEqual(
                    call["assistant_response"]["reasoning_content"], "Check the file."
                )
                self.assertEqual(
                    call["tool_calls"][0]["arguments"], {"path": "fixture.txt"}
                )
                self.assertEqual(
                    call["tool_observations"][0]["content"]["content"],
                    "public output " * 10000,
                )
            artifact = next((root / "artifacts").iterdir())
            artifact.write_bytes(b"corrupt")
            self.assertEqual(
                load_rollout(root, metadata={"reward": 1})["status"], "incomplete"
            )


if __name__ == "__main__":
    unittest.main()
