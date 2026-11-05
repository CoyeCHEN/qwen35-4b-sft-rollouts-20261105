"""Task admission, target coverage and independent-family split invariants."""

import copy
import importlib.util
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from sft.public_corpus import (
    admitted_records,
    build_corpus,
    coverage,
    uniform_segment_mean_weights,
)
from sft.teacher_segments import Decision, make_segments


def record(task="one", trial="a", **changes):
    value = {
        "pool": "calibforge",
        "task_id": task,
        "trial_id": trial,
        "family_id": task,
        "split": "train",
        "started_at": "2026-10-29T00:00:00Z",
        "qualified_success": True,
        "is_primary_trajectory": True,
        "classification": "QUALIFIED_SUCCESS",
        "student_proof": {
            key: True
            for key in (
                "semantic_projection_passed",
                "native_loader_and_collator_passed",
                "native_streaming_and_nonstreaming_parsers_passed",
                "all_original_targets_once",
            )
        },
    }
    value.update(changes)
    return value


def decision(ident, length):
    return Decision(
        ident,
        {
            "input_ids": list(range(length)),
            "labels": [-100] * (length - 2) + [length - 2, length - 1],
        },
        {
            "supervised_range": [length - 2, length],
            "generation_prefix_sha256": ident,
            "input_sha256": ident,
            "supervision_token_classes": {
                "thinking": 1,
                "thinking_boundary": 0,
                "body": 0,
                "action": 0,
                "ending": 1,
            },
        },
    )


class PublicCorpusTest(unittest.TestCase):
    def test_later_nicer_success_cannot_replace_the_first(self):
        first = record(is_primary_trajectory=False)
        later = record(trial="b", started_at="2026-10-29T01:00:00Z")
        with self.assertRaisesRegex(ValueError, "chronological first"):
            admitted_records([first, later], "calibforge")
        first["is_primary_trajectory"] = True
        later["is_primary_trajectory"] = False
        self.assertEqual(admitted_records([later, first], "calibforge"), [first])

    def test_primary_needs_complete_native_student_evidence(self):
        bad = record()
        bad["student_proof"]["native_loader_and_collator_passed"] = False
        with self.assertRaisesRegex(ValueError, "evidence incomplete"):
            admitted_records([bad], "calibforge")
        with self.assertRaisesRegex(ValueError, "another task pool"):
            admitted_records([record(pool="tmax")], "calibforge")

    def test_segment_mean_weight_is_distinct_from_token_share(self):
        mappings = [
            {"task_id": "a", "supervised_tokens": 2},
            {"task_id": "a", "supervised_tokens": 2},
            {"task_id": "b", "supervised_tokens": 6},
        ]
        result = uniform_segment_mean_weights(mappings)
        self.assertAlmostEqual(result["task_segment_share"]["a"], 2 / 3)
        self.assertAlmostEqual(result["task_supervised_token_share"]["a"], 0.4)
        self.assertEqual(result["per_token_coefficients"], [1 / 6, 1 / 6, 1 / 18])
        self.assertEqual(uniform_segment_mean_weights([])["task_segment_share"], {})
        with self.assertRaises(ValueError):
            uniform_segment_mean_weights([{"task_id": "bad", "supervised_tokens": 0}])

    def test_fixed_families_cannot_cross_split(self):
        with self.assertRaisesRegex(ValueError, "family crosses"):
            admitted_records(
                [record(), record(task="two", family_id="one", split="validation")],
                "calibforge",
            )

    def test_closing_target_and_all_targets_are_separate_counts(self):
        items = [
            decision("first", 10),
            decision("long-middle", 30),
            decision("close", 20),
        ]
        encoded = make_segments(items, cutoff=20)
        before = copy.deepcopy(encoded)
        stats = coverage(items, encoded)
        self.assertEqual(stats["retained_targets"], 2)
        self.assertTrue(stats["closing_target_retained"])
        self.assertFalse(stats["all_targets_retained"])
        self.assertEqual(
            stats["stage_target_counts"], {"early": 1, "middle": 0, "late": 1}
        )
        self.assertEqual(stats["supervised_tokens"], 4)
        self.assertEqual(encoded, before)
        self.assertFalse(
            coverage(items, make_segments(items, cutoff=10))["closing_target_retained"]
        )

    def test_multiple_targets_do_not_mean_multiple_samples_or_tasks(self):
        items = [decision("first", 10), decision("close", 20)]
        stats = coverage(items, make_segments(items, cutoff=20))
        self.assertEqual(stats["retained_targets"], 2)
        self.assertEqual(stats["segments"], 1)
        self.assertEqual(stats["multi_assistant_samples"], 1)
        self.assertTrue(stats["all_targets_retained"])

    @unittest.skipUnless(
        importlib.util.find_spec("datasets"), "Requires native Arrow cache dependency"
    )
    def test_build_roundtrips_both_fixed_splits_and_empty_views(self):
        from datasets import load_from_disk

        source = record(
            source_revision="revision",
            source_journal_sha256="journal",
            result_sha256="result",
        )
        source["student_proof"]["raw_export_sha256"] = "raw"
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "corpus"
            with patch(
                "sft.public_corpus.project_trial",
                return_value=[decision("first", 10), decision("close", 20)],
            ):
                manifest = build_corpus(
                    None,
                    pool="calibforge",
                    success_records=[source],
                    exports={"a": "raw.gz"},
                    output=output,
                    provenance={"test": True},
                )
            cache = load_from_disk(output / "cache-262144")
            self.assertEqual(len(cache["train"]), 1)
            self.assertEqual(len(cache["validation"]), 0)
            mapping = json.loads((output / "SAMPLE_MAPPING-262144.jsonl").read_text())
            self.assertEqual(mapping["cutoff"], 262144)
            self.assertEqual(
                [m["call_id"] for m in mapping["decision_mapping"]], ["first", "close"]
            )
            self.assertEqual(
                manifest["length_views"]["262144"]["train"]["retained_targets"], 2
            )
            self.assertFalse(manifest["released"])

    @unittest.skipUnless(
        importlib.util.find_spec("datasets"), "Requires native Arrow cache dependency"
    )
    def test_unconvertible_trace_never_leaks_a_text_prefix_into_the_cache(self):
        from datasets import load_from_disk

        source = record(
            source_revision="revision",
            source_journal_sha256="journal",
            result_sha256="result",
        )
        source["student_proof"]["raw_export_sha256"] = "raw"
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "quarantine"
            with patch(
                "sft.public_corpus.project_trial",
                side_effect=ValueError(
                    "Non-text content requires multimodal validation"
                ),
            ):
                manifest = build_corpus(
                    None,
                    pool="calibforge",
                    success_records=[source],
                    exports={"a": "raw.gz"},
                    output=output,
                    provenance={"test": True},
                )
            self.assertEqual(manifest["qualified_independent_tasks"], 1)
            self.assertEqual(manifest["semantically_projected_tasks"], 0)
            self.assertEqual(len(load_from_disk(output / "cache-262144")["train"]), 0)
            quarantine = json.loads((output / "QUARANTINE.json").read_text())
            self.assertEqual(len(quarantine), 1)
            self.assertEqual(quarantine[0]["trial_id"], "a")


@unittest.skipUnless(
    os.environ.get("QWEN35_NATIVE_AUDIT_TEST") == "1",
    "Requires pinned native LF/Qwen tokenizer environment; never loads a training model",
)
class NativePublicCorpusAuditTest(unittest.TestCase):
    def _audit_fixture(self, *, quarantined):
        from sft.public_corpus_audit import audit_corpus

        source = record(
            source_revision="unit-only",
            source_journal_sha256="unit-only",
            result_sha256="unit-only",
        )
        source["student_proof"]["raw_export_sha256"] = "unit-only"
        options = (
            {
                "side_effect": ValueError(
                    "Non-text content requires multimodal validation"
                )
            }
            if quarantined
            else {"return_value": [decision("unit-target", 32)]}
        )
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "unit-only-cache"
            with patch("sft.public_corpus.project_trial", **options):
                build_corpus(
                    None,
                    pool="calibforge",
                    success_records=[source],
                    exports={"a": "unit-only"},
                    output=output,
                    provenance={"unit_fixture": True, "training_admission": False},
                )
            return audit_corpus(output, model_path=os.environ["QWEN35_MODEL_PATH"])

    def test_native_nonempty_cache_checks_weights_labels_loss_and_gradients(self):
        result = self._audit_fixture(quarantined=False)
        self.assertTrue(result["passed"])
        self.assertTrue(result["sample_mean_weight_metadata_checked"])
        self.assertTrue(result["numerical_reference"]["passed"])
        self.assertFalse(result["cuda_initialized"])
        self.assertFalse(result["release_admission"])
        self.assertEqual(len(result["rows"]), 2)  # One row in each length view.

    def test_native_empty_cache_has_no_fabricated_numerical_targets(self):
        result = self._audit_fixture(quarantined=True)
        self.assertTrue(result["passed"])
        self.assertTrue(result["empty_corpus"])
        self.assertEqual(result["rows"], [])
        self.assertIsNone(result["numerical_reference"]["passed"])
        self.assertEqual(
            result["numerical_reference"]["status"],
            "NOT_APPLICABLE_NO_RETAINED_ROWS",
        )


if __name__ == "__main__":
    unittest.main()
