"""Prepare one explicitly named reproduction from approved inputs; never train.

Run on the authorized training host. Hashes are streamed and no tokenizer/model
is loaded. Original arms/results are not destinations for this command.
"""

import argparse
import hashlib
import json
import shutil
from pathlib import Path


def sha(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def prepare(arm, name, runtime, stage, model, data, report):
    source = Path(__file__).resolve().parent
    original = next(
        row
        for row in json.loads((source / "historical-arms.json").read_text())
        if row["name"] == arm
    )
    if name in {
        row["name"] for row in json.loads((source / "historical-arms.json").read_text())
    }:
        raise ValueError("Historical experiment IDs cannot be reused")
    runtime, stage, model, data = (
        Path(p).resolve() for p in (runtime, stage, model, data)
    )
    if stage.exists() or (runtime / "TRAINING_QUEUE-v5-observed.json").exists():
        raise ValueError(
            "Existing stage/queue: inspect artifacts, do not overwrite or redispatch"
        )
    expected_data = original["historical_identity"]["data"]
    if any(
        sha(data / (split + ".parquet")) != digest
        for split, digest in expected_data.items()
    ):
        raise ValueError(
            "Approved historical data SHA mismatch; a new data experiment requires a separate protocol"
        )
    stage.mkdir(parents=True)
    runtime.mkdir(parents=True, exist_ok=True)
    for directory in ("scripts", "sources", "training", "cache", "logs"):
        (runtime / directory).mkdir(exist_ok=True)
    for directory in ("scripts", "sources"):
        for path in (source / directory).glob("*.py"):
            dest = runtime / directory / path.name
            if dest.exists() and sha(dest) != sha(path):
                raise ValueError("Installed source differs: " + path.name)
            if not dest.exists():
                shutil.copy2(path, dest)
    (stage / "runs").mkdir()
    dataset = stage / "data/NiuNiu0110--TMax-Agent-SFT-terminus/data/pretokenized"
    dataset.mkdir(parents=True)
    for split in ("train", "holdout"):
        (dataset / (split + ".parquet")).symlink_to(data / (split + ".parquet"))
    (stage / "reports").mkdir()
    config = {**original["config"], "model_path": str(model)}
    report_name = config.get("validation_report", "data_validation.json")
    shutil.copy2(report, stage / "reports" / report_name)
    config_path = stage / "config.json"
    config_path.write_text(json.dumps(config, indent=2) + "\n")
    job = {
        "name": name,
        "stage": str(stage),
        "config": str(config_path),
        "precision": original["precision"],
        "gate": False,
        "expected_optimizer_steps": original["expected_optimizer_steps"],
        "identity": {
            "model_source": str(model),
            "input_model_sha256": sha(model / "model.safetensors"),
            "source_trainer_sha256": sha(runtime / "sources/original-train.py"),
            "candidate_sha256": sha(runtime / "scripts/training_candidate.py"),
            "config_sha256": sha(config_path),
            "data": {
                split: sha(data / (split + ".parquet"))
                for split in ("train", "holdout")
            },
        },
    }
    (runtime / "TRAINING_QUEUE-v5-observed.json").write_text(
        json.dumps({"jobs": [job]}, indent=2) + "\n"
    )
    return job


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    for option in ("arm", "name", "runtime", "stage", "model", "data", "report"):
        parser.add_argument("--" + option, required=True)
    print(json.dumps(prepare(**vars(parser.parse_args())), indent=2))
