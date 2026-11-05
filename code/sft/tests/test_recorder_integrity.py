"""Recorder completeness is independent of verifier reward and raw recovery."""
import copy
import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from adapters.openharness_v2 import load_rollout, load_rollouts
from sft.validation import TrajectoryInvalid, ensure_valid


class RecorderIntegrityTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        (self.root / "artifacts").mkdir()
        chunk = b'data: {"content":"hello"}\n\n'
        self.digest = hashlib.sha256(chunk).hexdigest()
        (self.root / "artifacts" / self.digest).write_bytes(chunk)
        self.ref = {"$artifact": self.digest, "size": len(chunk), "encoding": "utf-8"}
        self.manifest = {"schema_version": "open-harness-rollout-v2", "session_id": "session"}
        self.data = [
            ("run_start", {"run_id": "run"}),
            ("call_start", {"run_id": "run", "call_id": "call", "input": [{"role": "user", "content": "read"}]}),
            ("call_payload", {"run_id": "run", "call_id": "call", "payload": {"messages": [
                {"role": "system", "content": "system"}, {"role": "user", "content": "read"}]}, "fidelity": "provider_payload"}),
            ("call_chunk", {"run_id": "run", "call_id": "call", "chunk": self.ref}),
            ("call_end", {"run_id": "run", "call_id": "call", "status": "toolUse", "response": {
                "role": "assistant", "content": [{"type": "toolCall", "id": "tc", "name": "read", "arguments": {"path": "a"}}]}}),
            ("tool_start", {"run_id": "run", "call_id": "call", "execution_id": "exec", "tool_call_id": "tc", "name": "read"}),
            ("tool_raw", {"run_id": "run", "call_id": "call", "execution_id": "exec", "result": "hello"}),
            ("tool_end", {"run_id": "run", "call_id": "call", "execution_id": "exec", "status": "completed", "is_error": False}),
            ("run_end", {"run_id": "run", "status": "completed"}),
        ]

    def write(self, rows=None):
        (self.root / "manifest.json").write_text(json.dumps(self.manifest))
        events = [{"seq": i, "timestamp": i, "type": kind, "data": data}
                  for i, (kind, data) in enumerate(self.data if rows is None else rows, 1)]
        (self.root / "events.jsonl").write_text("".join(json.dumps(e) + "\n" for e in events))

    def load(self):
        return load_rollout(self.root, metadata={"reward": 1})

    def assert_incomplete(self):
        before = (self.root / "events.jsonl").read_bytes()
        row = self.load()
        self.assertEqual(row["status"], "incomplete")
        self.assertEqual(row["reward_status"], "positive")
        self.assertEqual(row["reward"], 1)
        self.assertTrue(row["metadata"]["recorder_integrity"]["issues"])
        with self.assertRaises(TrajectoryInvalid):
            ensure_valid(row, require_completed=True)
        self.assertEqual((self.root / "events.jsonl").read_bytes(), before)
        return row

    def test_complete_preserves_payload_system_and_observation(self):
        self.write()
        row = self.load()
        ensure_valid(row, require_completed=True)
        self.assertEqual(row["calls"][0]["request_messages"][0]["role"], "system")
        self.assertEqual(row["calls"][0]["tool_observations"][0]["content"], "hello")

    def test_missing_run_end_is_not_completed_even_with_positive_reward(self):
        self.write(self.data[:-1])
        self.assert_incomplete()

    def test_missing_run_start_is_incomplete(self):
        self.write(self.data[1:])
        self.assert_incomplete()

    def test_unclosed_call_or_tool_is_incomplete(self):
        for missing in ("call_end", "tool_end"):
            with self.subTest(missing=missing):
                self.write([row for row in self.data if row[0] != missing])
                self.assert_incomplete()

    def test_duplicate_end_events_are_incomplete(self):
        for kind in ("run_end", "call_end", "tool_end"):
            with self.subTest(kind=kind):
                rows = copy.deepcopy(self.data)
                index = next(i for i, row in enumerate(rows) if row[0] == kind)
                rows.insert(index + 1, copy.deepcopy(rows[index]))
                self.write(rows)
                self.assert_incomplete()

    def test_orphan_tool_and_run_mismatch_are_incomplete(self):
        for key, value in (("call_id", "missing"), ("run_id", "other")):
            with self.subTest(key=key):
                rows = copy.deepcopy(self.data)
                rows[5][1][key] = value
                self.write(rows)
                self.assert_incomplete()

    def test_events_after_run_end_are_incomplete(self):
        self.write(self.data[:5] + [self.data[-1]] + self.data[5:-1])
        self.assert_incomplete()

    def test_interrupted_run_is_incomplete(self):
        rows = copy.deepcopy(self.data)
        rows[-1][1]["status"] = "interrupted"
        self.write(rows)
        self.assert_incomplete()

    def test_corrupt_or_missing_artifact_retains_verified_prefix(self):
        for missing in (False, True):
            with self.subTest(missing=missing):
                artifact = self.root / "artifacts" / self.digest
                artifact.write_bytes(b"corrupt")
                if missing:
                    artifact.unlink()
                self.write()
                row = self.assert_incomplete()
                self.assertEqual(row["metadata"]["recorder_integrity"]["verified_prefix_events"], 3)
                self.assertEqual(len(row["calls"]), 1)

    def test_wrong_artifact_size_is_incomplete(self):
        self.ref["size"] += 1
        self.write()
        self.assert_incomplete()

    def test_truncated_or_invalid_sequence_retains_prefix(self):
        for suffix in (b'{"seq":', b'{"seq":123,"type":"run_end","data":{}}\n'):
            with self.subTest(suffix=suffix):
                self.write(self.data[:-1])
                with (self.root / "events.jsonl").open("ab") as stream:
                    stream.write(suffix)
                row = self.assert_incomplete()
                self.assertEqual(len(row["calls"]), 1)
                self.assertEqual(row["calls"][0]["tool_observations"][0]["content"], "hello")

    def test_complete_zero_reward_is_not_a_positive_training_sample(self):
        self.write()
        row = load_rollout(self.root, metadata={"reward": 0})
        self.assertEqual(row["status"], "completed")
        self.assertEqual(row["reward_status"], "zero")
        ensure_valid(row)
        with self.assertRaises(TrajectoryInvalid):
            ensure_valid(row, require_completed=True)

    def write_export(self, include_run=True):
        self.manifest["runs"] = ([{"run_id": "run", "started_at": 1, "ended_at": 9, "status": "completed"}]
                                 if include_run else [])
        (self.root / "manifest.json").write_text(json.dumps({"schema_version": "open-harness-rollout-v2", "sessions": [self.manifest]}))
        call = {**self.data[1][1], **self.data[4][1], "session_id": "session", "started_at": 2, "ended_at": 5}
        tool = {**self.data[5][1], **self.data[7][1], "session_id": "session", "started_at": 6, "ended_at": 8, "raw_result": "hello"}
        (self.root / "calls.jsonl").write_text(json.dumps(call) + "\n")
        (self.root / "tools.jsonl").write_text(json.dumps(tool) + "\n")

    def test_export_requires_run_evidence(self):
        self.write_export(include_run=False)
        row = self.load()
        self.assertEqual(row["status"], "incomplete")
        self.write_export()
        ensure_valid(self.load(), require_completed=True)

    def test_integrity_is_checked_per_session_in_export(self):
        self.write_export()
        manifest = json.loads((self.root / "manifest.json").read_text())
        other = {**self.manifest, "session_id": "other", "runs": []}
        manifest["sessions"].append(other)
        (self.root / "manifest.json").write_text(json.dumps(manifest))
        with (self.root / "calls.jsonl").open("a") as stream:
            row = json.loads((self.root / "calls.jsonl").read_text().splitlines()[0])
            row.update(session_id="other", response={"role": "assistant", "content": "done"})
            stream.write(json.dumps(row) + "\n")
        rows = load_rollouts(self.root, metadata={"reward": 1})
        self.assertEqual({row["trajectory_id"]: row["status"] for row in rows}, {"session": "completed", "other": "incomplete"})

    def test_orphan_stream_event_is_incomplete(self):
        rows = copy.deepcopy(self.data)
        rows[3][1]["call_id"] = "missing"
        self.write(rows)
        self.assert_incomplete()

    def test_export_cannot_put_a_call_outside_its_run(self):
        self.write_export()
        manifest = json.loads((self.root / "manifest.json").read_text())
        manifest["sessions"][0]["runs"][0]["ended_at"] = 3
        (self.root / "manifest.json").write_text(json.dumps(manifest))
        self.assertEqual(self.load()["status"], "incomplete")

    def test_export_requires_start_evidence(self):
        self.write_export()
        manifest = json.loads((self.root / "manifest.json").read_text())
        del manifest["sessions"][0]["runs"][0]["started_at"]
        (self.root / "manifest.json").write_text(json.dumps(manifest))
        self.assertEqual(self.load()["status"], "incomplete")

    def test_missing_tool_observation_is_incomplete(self):
        self.write([row for row in self.data if row[0] != "tool_raw"])
        self.assert_incomplete()

    def test_tool_end_result_is_preserved_when_raw_result_is_unavailable(self):
        rows = copy.deepcopy([row for row in self.data if row[0] != "tool_raw"])
        result = {"content": [{"type": "text", "text": "file not found"}]}
        end = next(row[1] for row in rows if row[0] == "tool_end")
        end.update(result=result, is_error=True, status="error")
        self.write(rows)
        row = self.load()
        ensure_valid(row, require_completed=True)
        self.assertEqual(row["calls"][0]["tool_observations"][0]["content"], result)

    def test_invalid_artifact_reference_is_incomplete(self):
        self.ref["$artifact"] = "../escape"
        self.write()
        self.assert_incomplete()

    def test_canonical_status_cannot_hide_integrity_issues(self):
        self.write(self.data[:-1])
        row = self.assert_incomplete()
        row["status"] = "completed"
        with self.assertRaises(TrajectoryInvalid):
            ensure_valid(row, require_completed=True)

    def test_export_requires_terminal_call_status(self):
        self.write_export()
        path = self.root / "calls.jsonl"
        row = json.loads(path.read_text())
        del row["status"]
        path.write_text(json.dumps(row) + "\n")
        self.assertEqual(self.load()["status"], "incomplete")

    def test_ambiguous_or_invalid_reward_does_not_make_a_training_sample(self):
        self.write()
        values = [{"accuracy": 0, "cost": 2}, {"success": True, "cost": 2},
                  {"accuracy": 1, "cost": float("inf")}, True, float("inf"), float("nan")]
        for value in values:
            with self.subTest(value=value):
                metadata = ({"verifier_result": {"rewards": value}} if isinstance(value, dict)
                            else {"reward": value})
                row = load_rollout(self.root, metadata=metadata)
                self.assertEqual(row["status"], "completed")
                self.assertEqual(row["reward_status"], "invalid")
                self.assertIsNone(row["reward"])
                with self.assertRaises(TrajectoryInvalid):
                    ensure_valid(row, require_completed=True)

    def test_explicit_primary_and_single_metric_reward_are_supported(self):
        self.write()
        for rewards in ({"reward": 1, "cost": 2}, {"accuracy": 1}):
            with self.subTest(rewards=rewards):
                row = load_rollout(self.root, metadata={"verifier_result": {"rewards": rewards}})
                ensure_valid(row, require_completed=True)
                self.assertEqual(row["reward"], 1)

    def test_canonical_boolean_or_infinite_reward_is_invalid(self):
        self.write()
        for value in (True, float("inf"), float("nan")):
            with self.subTest(value=value):
                row = self.load()
                row["reward"] = value
                with self.assertRaises(TrajectoryInvalid):
                    ensure_valid(row, require_completed=True)
