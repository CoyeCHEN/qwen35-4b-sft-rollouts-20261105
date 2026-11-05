#!/usr/bin/env python3
"""Build a wheel from an exact Git tree without modifying its checkout."""

import argparse
import hashlib
import json
import subprocess
import tarfile
import tempfile
from pathlib import Path


def build(source: Path, commit: str, output: Path, kind: str) -> Path:
    resolved = subprocess.check_output(
        ["git", "-C", str(source), "rev-parse", f"{commit}^{{commit}}"], text=True
    ).strip()
    output = output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    if list(output.glob("*.whl")) or (output / "artifact.json").exists():
        raise ValueError(
            "Use an empty artifact directory; previous builds are immutable"
        )
    with tempfile.TemporaryDirectory(prefix="harbor-rsi-build-") as temporary:
        root = Path(temporary)
        archive = root / "source.tar"
        subprocess.run(
            [
                "git",
                "-C",
                str(source),
                "archive",
                "--format=tar",
                f"--output={archive}",
                resolved,
            ],
            check=True,
        )
        checkout = root / "source"
        checkout.mkdir()
        with tarfile.open(archive) as bundle:
            bundle.extractall(checkout, filter="data")
        if kind == "harbor":
            identity = checkout / "src/harbor/extensions/rsi/build_identity.json"
            if not identity.parent.is_dir():
                raise ValueError(
                    "Selected commit does not contain the Harbor RSI extension"
                )
            identity.write_text(
                json.dumps({"harbor_commit": resolved, "source_dirty": False}) + "\n"
            )
        subprocess.run(
            ["uv", "build", "--wheel", "--out-dir", str(output)],
            cwd=checkout,
            check=True,
        )
    wheels = list(output.glob("*.whl"))
    if len(wheels) != 1:
        raise ValueError("Expected exactly one wheel")
    wheel = wheels[0]
    manifest = {
        "schema_version": 1,
        "kind": kind,
        "path": str(wheel),
        "sha256": hashlib.sha256(wheel.read_bytes()).hexdigest(),
        "source_commit": resolved,
        "provenance": "producer-verified",
        "build_method": "git archive of exact commit; uv build --wheel",
    }
    if kind == "harness":
        manifest["artifact"] = {
            "path": str(wheel),
            "sha256": manifest["sha256"],
            "harness_commit": resolved,
            "cli_contract": "openharness-cli-v1",
            "provenance": "producer-verified",
        }
    (output / "artifact.json").write_text(json.dumps(manifest, indent=2) + "\n")
    return wheel


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--commit", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--kind", choices=("harbor", "harness"), required=True)
    args = parser.parse_args()
    print(build(args.source.resolve(), args.commit, args.output, args.kind))


if __name__ == "__main__":
    main()
