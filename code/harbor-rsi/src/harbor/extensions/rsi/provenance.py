"""Content identities and atomic JSON evidence for native Campaigns."""

import hashlib
import json
import subprocess
import tempfile
from importlib.metadata import version
from importlib.resources import files
from pathlib import Path
from typing import Any

from harbor.extensions.rsi import UPSTREAM_COMMIT


def digest_json(value) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def write_json(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(mode="w", dir=path.parent, delete=False) as stream:
        temporary = Path(stream.name)
        json.dump(value, stream, indent=2, allow_nan=False)
        stream.write("\n")
    temporary.replace(path)


def code_identity() -> dict[str, Any]:
    import harbor

    root = Path(harbor.__file__).resolve().parents[2]
    identity: dict[str, Any] = {
        "harbor_version": version("harbor"),
        "upstream_commit": UPSTREAM_COMMIT,
        "harbor_commit": None,
        "source_dirty": None,
    }
    package_root = Path(harbor.__file__).resolve().parent
    digest = hashlib.sha256()
    for path in sorted(package_root.rglob("*")):
        if path.is_file() and "__pycache__" not in path.parts and path.suffix != ".pyc":
            digest.update(path.relative_to(package_root).as_posix().encode() + b"\0")
            digest.update(hashlib.sha256(path.read_bytes()).digest())
    identity["installed_package_sha256"] = digest.hexdigest()
    provenance = files("harbor.extensions.rsi").joinpath("build_identity.json")
    if provenance.is_file():
        identity.update(json.loads(provenance.read_text()))
    if (root / ".git").exists():
        identity["harbor_commit"] = subprocess.check_output(
            ["git", "-C", str(root), "rev-parse", "HEAD"], text=True
        ).strip()
        identity["source_dirty"] = bool(
            subprocess.check_output(
                ["git", "-C", str(root), "status", "--porcelain"], text=True
            ).strip()
        )
    return identity
