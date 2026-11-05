"""Actual official-template tests; use the pinned tokenizer from QWEN35_MODEL_PATH."""

import unittest

from sft.qwen35 import load_tokenizer
from sft.teacher_segments import make_segments, project_decision


def call(ident, history, reasoning="think", content="answer", tools=None):
    return dict(
        call_id=ident,
        context_fidelity="provider_payload",
        provider_payload=dict(messages=history, tools=tools),
        assistant_response=dict(
            role="assistant", reasoning_content=reasoning, content=content
        ),
    )


class TeacherSegmentsTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tokenizer = load_tokenizer()

    def test_official_input_nfc_preserves_serving_prefix_and_exact_target(self):
        source = call("nfc-history", [dict(role="user", content="Observe e\u0301")])
        tokenizer = self.tokenizer
        native = tokenizer.apply_chat_template(
            source["provider_payload"]["messages"], tokenize=True,
            return_dict=False, add_generation_prompt=True, enable_thinking=True,
        )
        decision = project_decision(tokenizer, source)
        left, right = decision.evidence["supervised_range"]
        self.assertEqual(decision.row["input_ids"][:left], native)
        self.assertEqual(decision.row["labels"][:left], [-100] * len(native))
        self.assertTrue(decision.evidence["input_prefix_normalized_by_official_tokenizer"])
        self.assertTrue(decision.evidence["target_text_roundtrip_exact"])
        self.assertEqual(
            tokenizer.decode(decision.row["labels"][left:right], clean_up_tokenization_spaces=False),
            "think\n</think>\n\nanswer<|im_end|>",
        )

    def test_target_nfc_changes_are_rejected_without_rewriting(self):
        source = call("nfc-target", [dict(role="user", content="Question")], content="e\u0301")
        with self.assertRaisesRegex(ValueError, "Generation-boundary tokenization changed"):
            project_decision(self.tokenizer, source)
        self.assertEqual(source["assistant_response"]["content"], "e\u0301")

    def test_target_tool_argument_nfc_changes_are_rejected(self):
        source = call("nfc-argument", [dict(role="user", content="Write text")], content="")
        source["assistant_response"]["tool_calls"] = [dict(
            id="write-nfd", type="function",
            function=dict(name="write", arguments='{"path":"/tmp/x","content":"e\u0301"}'),
        )]
        with self.assertRaisesRegex(ValueError, "Generation-boundary tokenization changed"):
            project_decision(self.tokenizer, source)

    def test_invalid_unicode_prefix_is_not_silently_repaired(self):
        source = call("invalid-unicode", [dict(role="user", content="bad\ud800")])
        with self.assertRaises((UnicodeError, TypeError, ValueError)):
            project_decision(self.tokenizer, source)

    def test_empty_thinking_preserves_deployed_prefix_tokens(self):
        source = call("empty", [dict(role="user", content="Question")], reasoning="")
        decision = project_decision(self.tokenizer, source)
        self.assertTrue(decision.evidence["generation_boundary_changes_bpe"])
        prefix = self.tokenizer.apply_chat_template(
            source["provider_payload"]["messages"],
            tokenize=True,
            return_dict=False,
            add_generation_prompt=True,
            enable_thinking=True,
        )
        self.assertEqual(decision.row["input_ids"][: len(prefix)], prefix)
        self.assertEqual(decision.row["labels"][: len(prefix)], [-100] * len(prefix))

    def test_eos_is_supervised_and_post_eos_separator_is_input_only(self):
        decision = project_decision(
            self.tokenizer, call("eos", [dict(role="user", content="Question")])
        )
        self.assertEqual(decision.row["labels"][-1], -100)
        self.assertEqual(
            self.tokenizer.decode([decision.row["labels"][-2]]), "<|im_end|>"
        )
        self.assertEqual(decision.evidence["supervision_token_classes"]["ending"], 1)

    def test_generation_thinking_opener_is_input_and_target_once(self):
        tokenizer = self.tokenizer
        d = project_decision(
            tokenizer, call("a", [dict(role="user", content="Question")])
        )
        left, right = d.evidence["supervised_range"]
        assert tokenizer.decode(d.row["input_ids"][:left]).endswith("<think>\n")
        assert tokenizer.decode(d.row["labels"][left:right]).startswith(
            "think\n</think>"
        )
        assert all(x == -100 for x in d.row["labels"][:left])
        result = make_segments([d], cutoff=262144)
        assert result["all_targets_exactly_once"]

    def test_new_user_changes_historical_thinking_and_forces_segments(self):
        tokenizer = self.tokenizer
        first = call("a", [dict(role="user", content="One")])
        second = call(
            "b",
            first["provider_payload"]["messages"]
            + [first["assistant_response"], dict(role="user", content="Two")],
        )
        decisions = [project_decision(tokenizer, x) for x in [first, second]]
        result = make_segments(decisions, cutoff=262144)
        assert len(result["samples"]) == 2
        assert result["target_count"] == 2
        second_row = result["samples"][1]["row"]
        assert all(
            x == -100
            for x in second_row["labels"][: decisions[1].evidence["prefix_tokens"]]
        )

    def test_unchanged_multi_assistant_history_can_share_one_segment(self):
        tokenizer = self.tokenizer
        first = call("a", [dict(role="user", content="Question")], content="First part")
        second = call(
            "b",
            first["provider_payload"]["messages"] + [first["assistant_response"]],
            content="Last part",
        )
        result = make_segments(
            [project_decision(tokenizer, x) for x in [first, second]], cutoff=262144
        )
        assert len(result["samples"]) == 1
        assert len(result["samples"][0]["evidence"]["decision_mapping"]) == 2

    def test_real_tool_observation_and_failed_tool_are_masked(self):
        tokenizer = self.tokenizer
        first = call("a", [dict(role="user", content="Use bash")], content="")
        first["assistant_response"]["tool_calls"] = [
            dict(
                id="c",
                type="function",
                function=dict(name="bash", arguments='{"command":"false"}'),
            )
        ]
        history = first["provider_payload"]["messages"] + [
            first["assistant_response"],
            dict(
                role="tool", tool_call_id="c", content="exit 1; actual budget preview"
            ),
        ]
        second = call("b", history, content="Repair")
        decisions = [project_decision(tokenizer, x) for x in [first, second]]
        result = make_segments(decisions, cutoff=262144)
        assert len(result["samples"]) == 1
        row = result["samples"][0]["row"]
        supervised = tokenizer.decode([x for x in row["labels"] if x != -100])
        assert "actual budget preview" not in supervised
        assert "false" in supervised

    def test_compacted_real_context_and_overlong_target_are_explicit(self):
        tokenizer = self.tokenizer
        a = project_decision(
            tokenizer, call("a", [dict(role="user", content="Original")])
        )
        b = project_decision(
            tokenizer, call("b", [dict(role="user", content="Actual summary context")])
        )
        result = make_segments([a, b], cutoff=262144)
        assert len(result["samples"]) == 2
        quarantined = make_segments([a], cutoff=len(a.row["input_ids"]) - 1)
        assert not quarantined["all_targets_exactly_once"]
        assert quarantined["target_count"] == 0
        assert quarantined["quarantine"][0]["call_id"] == "a"


if __name__ == "__main__":
    unittest.main()
