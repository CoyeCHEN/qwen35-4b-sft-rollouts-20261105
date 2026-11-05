"""Normalize an offline OCI archive name without changing any image blob.

containerd preserves OCI reference annotations verbatim. A Docker Hub short
name can therefore be loaded successfully yet be undiscoverable by Docker's
normalized lookup. This deployment utility writes a new archive and receipt;
it never contacts a daemon, pulls an image, or alters the input archive.
"""

import argparse
import hashlib
import io
import json
import re
import tarfile
from pathlib import Path, PurePosixPath
from typing import Any

from benchmarks.readiness.prepare_verifier_cache import sha256


def canonicalize(
    source: Path,
    destination: Path,
    source_sha256: str,
    manifest_digest: str,
    config_digest: str,
    image_name: str,
    max_bytes: int = 1024 * 1024 * 1024,
) -> dict[str, Any]:
    if destination.exists():
        raise ValueError("Destination already exists; refusing overwrite")
    if source.stat().st_size > max_bytes:
        raise ValueError("Archive exceeds authorized byte bound")
    if sha256(source) != source_sha256:
        raise ValueError("Source archive SHA-256 mismatch")
    if not all(
        re.fullmatch(r"sha256:[a-f0-9]{64}", digest)
        for digest in [manifest_digest, config_digest]
    ):
        raise ValueError("Invalid image digest")
    if not re.fullmatch(r"[a-z0-9][a-z0-9./:_-]+:[A-Za-z0-9_.-]+", image_name):
        raise ValueError("An explicit image tag is required")
    prefix = image_name.split("/")[0]
    canonical_name = (
        image_name
        if "/" in image_name
        and ("." in prefix or ":" in prefix or prefix == "localhost")
        else "docker.io/" + image_name
        if "/" in image_name
        else "docker.io/library/" + image_name
    )
    with tarfile.open(source) as archive:
        members = archive.getmembers()
        names = set()
        for member in members:
            name = PurePosixPath(member.name)
            if (
                name.is_absolute()
                or ".." in name.parts
                or name.as_posix() != member.name.rstrip("/")
                or member.name in names
                or not (member.isfile() or member.isdir())
            ):
                raise ValueError(f"Unsafe archive member: {member.name}")
            names.add(member.name)

        def read_json(name: str) -> dict[str, Any]:
            member = archive.getmember(name)
            if member.size > 8 * 1024 * 1024:
                raise ValueError("Image metadata exceeds byte bound")
            stream = archive.extractfile(member)
            if stream is None:
                raise ValueError("Missing image metadata")
            return json.load(stream)

        index = read_json("index.json")
        if (
            len(index.get("manifests", [])) != 1
            or index["manifests"][0]["digest"] != manifest_digest
        ):
            raise ValueError("Archive must contain the one frozen platform manifest")
        manifest = read_json("blobs/sha256/" + manifest_digest.split(":")[1])
        if manifest["config"]["digest"] != config_digest:
            raise ValueError("Frozen config digest mismatch")
        config = read_json("blobs/sha256/" + config_digest.split(":")[1])
        if config.get("os") != "linux" or config.get("architecture") != "amd64":
            raise ValueError("Expected linux/amd64 image")
        expected = {manifest_digest, config_digest} | {
            layer["digest"] for layer in manifest["layers"]
        }
        seen = set()
        for member in members:
            if member.isfile() and member.name.startswith("blobs/sha256/"):
                stream = archive.extractfile(member)
                if stream is None:
                    raise ValueError("Missing blob")
                digest = hashlib.sha256()
                while block := stream.read(1024 * 1024):
                    digest.update(block)
                actual = "sha256:" + digest.hexdigest()
                if actual != "sha256:" + member.name.split("/")[-1]:
                    raise ValueError("Blob SHA-256 mismatch")
                seen.add(actual)
        if seen != expected:
            raise ValueError("Archive has missing or unexpected image blobs")
        annotations = index["manifests"][0].setdefault("annotations", {})
        annotations["io.containerd.image.name"] = canonical_name
        annotations["org.opencontainers.image.ref.name"] = canonical_name
        destination.parent.mkdir(parents=True, exist_ok=True)
        try:
            with tarfile.open(destination, "x") as output:
                for member in members:
                    stream = archive.extractfile(member) if member.isfile() else None
                    if member.name == "index.json":
                        payload = json.dumps(index, separators=(",", ":")).encode()
                        member.size = len(payload)
                        stream = io.BytesIO(payload)
                    output.addfile(member, stream)
        except BaseException:
            destination.unlink(missing_ok=True)
            raise
    return {
        "source_archive_sha256": source_sha256,
        "canonical_archive_sha256": sha256(destination),
        "platform_manifest_digest": manifest_digest,
        "config_digest": config_digest,
        "verified_blob_count": len(seen),
        "canonical_reference": canonical_name,
        "platform": "linux/amd64",
        "image_blobs_changed": False,
        "daemon_imported": False,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--destination", type=Path, required=True)
    parser.add_argument("--source-sha256", required=True)
    parser.add_argument("--manifest-digest", required=True)
    parser.add_argument("--config-digest", required=True)
    parser.add_argument("--image-name", required=True)
    parser.add_argument("--max-bytes", type=int, default=1024 * 1024 * 1024)
    parser.add_argument("--receipt", type=Path, required=True)
    args = parser.parse_args()
    receipt = canonicalize(
        args.source,
        args.destination,
        args.source_sha256,
        args.manifest_digest,
        args.config_digest,
        args.image_name,
        args.max_bytes,
    )
    args.receipt.write_text(json.dumps(receipt, indent=2) + "\n")


if __name__ == "__main__":
    main()
