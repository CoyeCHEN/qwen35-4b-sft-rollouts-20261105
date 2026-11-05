import json
import os
import tempfile
import unittest
from pathlib import Path

from adapters.openharness_v2 import load_rollout as load_openharness
from adapters.rlbridge import load_rollout as load_rlbridge
from sft.validation import TrajectoryInvalid, ensure_valid, validate_trajectory


ROOT = Path(__file__).parents[1]


class AdapterTests(unittest.TestCase):
    def test_openharness_fixture_pairs_tool(self):
        row = load_openharness(ROOT / "fixtures/openharness_v2")
        self.assertEqual(row["source"], "openharness_v2")
        self.assertEqual(row["calls"][0]["tool_calls"][0]["id"], "tc-1")
        self.assertEqual(row["calls"][0]["tool_observations"][0]["content"], "hello")
        ensure_valid(row)

    def test_openharness_export_fixture_is_supported(self):
        row = load_openharness(ROOT / "fixtures/openharness_v2_export")
        self.assertEqual(row["calls"][0]["tool_observations"][0]["content"], "hello")
        ensure_valid(row)

    def test_rlbridge_fixture_has_reward_and_tool(self):
        row = load_rlbridge(ROOT / "fixtures/rlbridge/rollout.json")
        self.assertEqual(row["reward"], 1)
        self.assertEqual(row["reward_status"], "positive")
        ensure_valid(row)

    def test_missing_rlbridge_observation_is_marked(self):
        path = ROOT / "fixtures/rlbridge/rollout.json"
        payload = json.loads(path.read_text())
        payload["messages"] = payload["messages"][:2]
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "x.json"
            target.write_text(json.dumps(payload))
            row = load_rlbridge(target)
        self.assertEqual(row["status"], "incomplete")
        self.assertTrue(row["metadata"]["validation_issues"])
        self.assertIn("missing observation", str(row["metadata"]["validation_issues"]))

    def test_duplicate_call_id_is_rejected_by_validation(self):
        row = load_openharness(ROOT / "fixtures/openharness_v2")
        row["calls"].append(dict(row["calls"][0]))
        issues = validate_trajectory(row)
        self.assertTrue(any("duplicate call ID" in issue.message for issue in issues))
        with self.assertRaises(TrajectoryInvalid):
            ensure_valid(row)

    def test_missing_tool_call_id_is_rejected(self):
        row = load_openharness(ROOT / "fixtures/openharness_v2")
        row["calls"][0]["tool_calls"][0]["id"] = None
        self.assertTrue(validate_trajectory(row))

    def test_zero_reward_is_distinct_from_missing(self):
        row = load_openharness(ROOT / "fixtures/openharness_v2", metadata={"reward": 0})
        self.assertEqual(row["reward"], 0)
        self.assertEqual(row["reward_status"], "zero")

    def test_real_harbor_recorder_preserves_provider_payload_and_reward(self):
        configured = os.environ.get("OPENHARNESS_REAL_TRIAL_DIR")
        if not configured:
            self.skipTest("set OPENHARNESS_REAL_TRIAL_DIR for real Harbor evidence")
        source = Path(configured)
        rollout = source / "agent" / "openharness-rollout"
        if not rollout.is_dir():
            self.skipTest("real Harbor smoke evidence is unavailable")
        metadata = json.loads((source / "result.json").read_text())
        row = load_openharness(
            rollout,
            metadata={
                **metadata,
                "trial_id": metadata["id"],
                "task_id": metadata["task_name"],
            },
            trial_dir=source,
        )
        self.assertEqual(row["trial_id"], metadata["id"])
        self.assertEqual(row["reward"], 1.0)
        self.assertEqual(row["reward_status"], "positive")
        self.assertEqual(len(row["calls"]), 3)
        self.assertTrue(all(call["provider_payload"] for call in row["calls"]))
        self.assertEqual(sum(len(call["tool_calls"]) for call in row["calls"]), 2)
        self.assertEqual([len(call["request_messages"]) for call in row["calls"]], [2, 4, 6])
        self.assertEqual(row["calls"][0]["request_messages"][0]["role"], "system")
        historical = row["calls"][1]["request_messages"][2]["tool_calls"][0]
        self.assertIsInstance(historical["function"]["arguments"], dict)
