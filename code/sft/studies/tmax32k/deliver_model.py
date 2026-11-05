"""Produce an exclusive model descriptor after verifying immutable Final files."""

import argparse
import hashlib
import json
from pathlib import Path


def descriptor(model, expected):
    model = Path(model).resolve()

    def sha(path):
        with path.open("rb") as stream:
            return hashlib.file_digest(stream, "sha256").hexdigest()

    actual = sha(model / "model.safetensors")
    if actual != expected:
        raise ValueError("Final weight SHA mismatch")
    files = {}
    for name in (
        "config.json",
        "tokenizer.json",
        "tokenizer_config.json",
        "chat_template.jinja",
        "generation_config.json",
    ):
        files[name] = sha(model / name)
    return {"path": str(model), "sha256": actual, "auxiliary_files": files}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", required=True)
    parser.add_argument("--sha256", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    result = descriptor(args.model, args.sha256)
    with Path(args.output).open("x") as stream:
        stream.write(json.dumps(result, indent=2) + "\n")
