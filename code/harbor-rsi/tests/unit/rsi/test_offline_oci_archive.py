"""Offline OCI naming preparation preserves the verified image bytes."""

import hashlib
import io
import json
import tarfile
from pathlib import Path

import pytest

from benchmarks.readiness.canonicalize_oci_archive import canonicalize
from benchmarks.readiness.prepare_verifier_cache import sha256


def fixture(
    path: Path, *, architecture: str = "amd64", unsafe: bool = False
) -> tuple[str, str, dict[str, bytes]]:
    files: dict[str, bytes] = {}

    def blob(data: bytes) -> str:
        digest = "sha256:" + hashlib.sha256(data).hexdigest()
        files["blobs/sha256/" + digest.split(":")[1]] = data
        return digest

    config = blob(json.dumps({"os": "linux", "architecture": architecture}).encode())
    layer = blob(b"verified layer fixture")
    manifest = blob(
        json.dumps(
            {"config": {"digest": config}, "layers": [{"digest": layer}]}
        ).encode()
    )
    files["index.json"] = json.dumps(
        {
            "schemaVersion": 2,
            "manifests": [
                {
                    "digest": manifest,
                    "annotations": {
                        "org.opencontainers.image.ref.name": "owner/task:pin"
                    },
                }
            ],
        }
    ).encode()
    files["oci-layout"] = b'{"imageLayoutVersion":"1.0.0"}'
    if unsafe:
        files["../outside"] = b"bad archive member"
    with tarfile.open(path, "w") as archive:
        for name, data in files.items():
            member = tarfile.TarInfo(name)
            member.size = len(data)
            archive.addfile(member, io.BytesIO(data))
    return manifest, config, files


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("owner/task:pin", "docker.io/owner/task:pin"),
        ("ubuntu:pin", "docker.io/library/ubuntu:pin"),
        ("registry.example/owner/task:pin", "registry.example/owner/task:pin"),
        (
            "registry.example:5000/owner/task:pin",
            "registry.example:5000/owner/task:pin",
        ),
    ],
)
def test_only_archive_index_name_changes(
    tmp_path: Path, name: str, expected: str
) -> None:
    source, destination = tmp_path / "source.tar", tmp_path / "canonical.tar"
    manifest, config, original = fixture(source)
    digest = sha256(source)
    receipt = canonicalize(source, destination, digest, manifest, config, name)
    assert sha256(source) == digest
    assert not receipt["image_blobs_changed"] and not receipt["daemon_imported"]
    with tarfile.open(destination) as archive:
        for key, data in original.items():
            stream = archive.extractfile(key)
            assert stream is not None
            if key != "index.json":
                assert stream.read() == data
            else:
                index = json.load(stream)
                assert index["manifests"][0]["digest"] == manifest
                assert (
                    index["manifests"][0]["annotations"]["io.containerd.image.name"]
                    == expected
                )
    with pytest.raises(ValueError, match="already exists"):
        canonicalize(source, destination, digest, manifest, config, name)


def test_bounds_and_identity_are_checked_before_output(tmp_path: Path) -> None:
    source, destination = tmp_path / "source.tar", tmp_path / "canonical.tar"
    manifest, config, _ = fixture(source)
    digest = sha256(source)
    with pytest.raises(ValueError, match="byte bound"):
        canonicalize(source, destination, digest, manifest, config, "owner/task:pin", 1)
    with pytest.raises(ValueError, match="Source archive"):
        canonicalize(source, destination, "0" * 64, manifest, config, "owner/task:pin")
    with pytest.raises(ValueError, match="platform manifest"):
        canonicalize(
            source, destination, digest, "sha256:" + "0" * 64, config, "owner/task:pin"
        )
    with pytest.raises(ValueError, match="explicit image tag"):
        canonicalize(source, destination, digest, manifest, config, "owner/task")
    assert not destination.exists()


@pytest.mark.parametrize("case", ["architecture", "unsafe"])
def test_wrong_platform_and_unsafe_archives_are_refused(
    tmp_path: Path, case: str
) -> None:
    source, destination = tmp_path / "source.tar", tmp_path / "canonical.tar"
    manifest, config, _ = fixture(
        source,
        architecture="arm64" if case == "architecture" else "amd64",
        unsafe=case == "unsafe",
    )
    with pytest.raises(ValueError):
        canonicalize(
            source, destination, sha256(source), manifest, config, "owner/task:pin"
        )
    assert not destination.exists()
