import unittest
from pathlib import Path

from adapters.openharness_v2 import load_rollout
from sft.tokenization import _messages_for_call, tokenize_trajectories


class FakeTokenizer:
    def apply_chat_template(self, messages, **kwargs):
        self.messages = messages
        self.options = kwargs
        return {"input_ids": [10, 11, 12, 13], "assistant_masks": [0, 0, 1, 1]}


class TokenizationTests(unittest.TestCase):
    def test_provider_tool_definitions_reach_student_template(self):
        root = Path(__file__).parents[1]
        row = load_rollout(root / "fixtures/openharness_v2")
        tools = [{"type": "function", "function": {"name": "shell", "parameters": {
            "type": "object", "properties": {"command": {"type": "string"}},
            "required": ["command"],
        }}}]
        row["calls"][0]["provider_payload"]["tools"] = tools
        tokenizer = FakeTokenizer()
        tokenize_trajectories([row], tokenizer)
        self.assertEqual(tokenizer.options["tools"], tools)

    def test_real_adapter_output_gets_assistant_only_mask(self):
        root = Path(__file__).parents[1]
        row = load_rollout(root / "fixtures/openharness_v2")
        output = tokenize_trajectories([row], FakeTokenizer(), max_length=8)
        self.assertEqual(output[0]["labels"], [-100, -100, 12, 13])
        self.assertEqual(output[0]["loss_mask"], [0, 0, 1, 1])

    def test_overlength_is_rejected(self):
        root = Path(__file__).parents[1]
        row = load_rollout(root / "fixtures/openharness_v2")
        with self.assertRaises(ValueError):
            tokenize_trajectories([row], FakeTokenizer(), max_length=3)

    def test_duplicate_assistant_history_is_rejected(self):
        root = Path(__file__).parents[1]
        row = load_rollout(root / "fixtures/openharness_v2")
        row["calls"][0]["request_messages"].append({"role": "assistant", "content": "already rendered"})
        with self.assertRaises(ValueError):
            tokenize_trajectories([row], FakeTokenizer())

    def test_only_current_call_response_is_marked(self):
        root = Path(__file__).parents[1]
        trajectory = load_rollout(root / "fixtures/openharness_v2")
        first = trajectory["calls"][0]
        second = {
            "call_id": "call-2",
            "request_messages": first["request_messages"] + [first["assistant_response"], {
                "role": "tool", "content": "hello", "tool_call_id": "tc-1"
            }],
            "assistant_response": {"role": "assistant", "content": "done"},
            "tool_calls": [], "tool_observations": [],
            "context_fidelity": "provider_payload",
        }
        assistant_messages = [m for m in _messages_for_call(second) if m.get("role") == "assistant"]
        self.assertEqual([m["step_loss_mask"] for m in assistant_messages], [0, 1])
