"""Copy a closed, verified training artifact to approved persistent storage.

Single CPU worker, streaming hashes, no model/GPU loading. A partial destination
is retained on failure and is never accepted as an archive receipt.
"""

import argparse
import hashlib
import json
import os
import shutil
from pathlib import Path


def sha(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def commit(source, destination):
    source, destination = Path(source), Path(destination)
    status = json.loads((source / "execution-status.json").read_text())
    if status["state"] != "COMPLETED":
        raise ValueError("Trainer is not in verified completed state")
    manifest_path = source / "artifact-manifest.json"
    manifest_sha = sha(manifest_path)
    manifest = json.loads(manifest_path.read_text())
    destination.mkdir(parents=True, exist_ok=False)
    for name, expected in manifest["files"].items():
        relative = Path(name)
        if relative.is_absolute() or ".." in relative.parts:
            raise ValueError("Artifact path escapes archive")
        original, target = source / relative, destination / relative
        if sha(original) != expected["sha256"]:
            raise ValueError("Closed source SHA mismatch: " + name)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(original, target)
        with target.open("rb") as stream:
            os.fsync(stream.fileno())
        if sha(target) != expected["sha256"]:
            raise ValueError("Persistent copy SHA mismatch: " + name)
    for name in (
        "artifact-manifest.json",
        "execution-status.json",
        "config.json",
        "input-verification.json",
    ):
        if (source / name).exists():
            shutil.copy2(source / name, destination / name)
    if sha(manifest_path) != manifest_sha:
        raise ValueError("Source manifest changed during archival")
    # Persist files and directory entries before the final receipt is visible.
    for path in destination.rglob("*"):
        if path.is_file():
            with path.open("rb") as stream:
                os.fsync(stream.fileno())
    receipt = {
        "status": "VERIFIED_PERSISTENT_ARCHIVE",
        "source_manifest_sha256": manifest_sha,
        "files_verified": len(manifest["files"]),
        "gpu_loaded": False,
    }
    temp = destination / "archive-receipt.pending"
    with temp.open("x") as stream:
        stream.write(json.dumps(receipt, indent=2) + "\n")
        stream.flush()
        os.fsync(stream.fileno())
    for directory in [p for p in destination.rglob("*") if p.is_dir()] + [destination]:
        fd = os.open(directory, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)
    temp.rename(destination / "archive-receipt.json")
    fd = os.open(destination, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)
    return receipt


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", required=True)
    parser.add_argument("--destination", required=True)
    print(json.dumps(commit(**vars(parser.parse_args())), indent=2))
