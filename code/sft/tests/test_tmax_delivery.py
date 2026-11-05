"""Small CPU fixtures for immutable model/experiment identities."""

import hashlib
import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path

STUDY = Path(__file__).resolve().parents[1] / "studies/tmax32k"


def module(name):
    spec = importlib.util.spec_from_file_location(name, STUDY / (name + ".py"))
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


@unittest.skipUnless(
    sys.version_info >= (3, 12), "TMax study runtime requires Python 3.12+"
)
class Delivery(unittest.TestCase):
    def test_final_sha_mismatch_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "model.safetensors").write_bytes(b"fixture weight")
            with self.assertRaisesRegex(ValueError, "weight SHA mismatch"):
                module("deliver_model").descriptor(root, "0" * 64)

    def test_model_and_tokenizer_identity_are_bound(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for name in (
                "model.safetensors",
                "config.json",
                "tokenizer.json",
                "tokenizer_config.json",
                "chat_template.jinja",
                "generation_config.json",
            ):
                (root / name).write_bytes(b"public fixture")
            digest = hashlib.sha256(b"public fixture").hexdigest()
            result = module("deliver_model").descriptor(root, digest)
            self.assertEqual(result["sha256"], digest)
            self.assertEqual(len(result["auxiliary_files"]), 5)

    def test_historical_arm_ids_cannot_be_retrained(self):
        arm = json.loads((STUDY / "historical-arms.json").read_text())[0]["name"]
        with (
            tempfile.TemporaryDirectory() as tmp,
            self.assertRaisesRegex(ValueError, "Historical experiment IDs"),
        ):
            module("prepare_arm").prepare(
                arm, arm, Path(tmp) / "runtime", Path(tmp) / "stage", tmp, tmp, tmp
            )

    def test_existing_training_queue_cannot_be_overwritten(self):
        arm = json.loads((STUDY / "historical-arms.json").read_text())[0]["name"]
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            queue = root / "TRAINING_QUEUE-v5-observed.json"
            queue.write_text("already prepared")
            with self.assertRaisesRegex(ValueError, "Existing stage/queue"):
                module("prepare_arm").prepare(
                    arm,
                    "new-explicit-experiment",
                    root,
                    root / "stage",
                    root,
                    root,
                    root,
                )
            self.assertEqual(queue.read_text(), "already prepared")

    def test_unapproved_data_is_rejected_before_stage_creation(self):
        arm = json.loads((STUDY / "historical-arms.json").read_text())[0]["name"]
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for split in ("train", "holdout"):
                (root / (split + ".parquet")).write_bytes(b"different public fixture")
            with self.assertRaisesRegex(ValueError, "data SHA mismatch"):
                module("prepare_arm").prepare(
                    arm,
                    "new-explicit-experiment",
                    root / "runtime",
                    root / "stage",
                    root,
                    root,
                    root,
                )
            self.assertFalse((root / "stage").exists())


@unittest.skipUnless(
    sys.version_info >= (3, 12), "TMax study runtime requires Python 3.12+"
)
class Archive(unittest.TestCase):
    def test_closed_archive_copies_verifies_and_never_overwrites(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "source"
            source.mkdir()
            dest = root / "archive"
            (source / "execution-status.json").write_text('{"state":"COMPLETED"}')
            (source / "weight").write_bytes(b"closed fixture")
            digest = hashlib.sha256(b"closed fixture").hexdigest()
            (source / "artifact-manifest.json").write_text(
                json.dumps({"files": {"weight": {"sha256": digest}}})
            )
            result = module("commit_archive").commit(source, dest)
            self.assertEqual(result["status"], "VERIFIED_PERSISTENT_ARCHIVE")
            self.assertEqual((dest / "weight").read_bytes(), b"closed fixture")
            with self.assertRaises(FileExistsError):
                module("commit_archive").commit(source, dest)

    def test_running_or_corrupt_archive_never_publishes_receipt(self):
        for state in ("RUNNING", "COMPLETED"):
            with self.subTest(state=state), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                source = root / "source"
                source.mkdir()
                dest = root / "archive"
                (source / "execution-status.json").write_text(
                    json.dumps({"state": state})
                )
                (source / "weight").write_bytes(b"corrupt")
                (source / "artifact-manifest.json").write_text(
                    json.dumps({"files": {"weight": {"sha256": "0" * 64}}})
                )
                with self.assertRaises(ValueError):
                    module("commit_archive").commit(source, dest)
                self.assertFalse((dest / "archive-receipt.json").exists())


if __name__ == "__main__":
    unittest.main()
