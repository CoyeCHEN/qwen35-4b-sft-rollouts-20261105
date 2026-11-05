"""Fetch pinned agent inputs/rubrics only; never expose grader search materials."""

import argparse
import concurrent.futures
import hashlib
import json
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

REVISION = "d43a66575635da0d3f6cb9a20976dc1a60f3ffc9"
REPOSITORY = "JobBench/job-bench"
TREE_SHA256 = "bfdd34d99d3e4a186eba82b396fe9e8c69a55f2aef0dab32a8c4bac1f693c63c"


def selected_entries(tree: Path) -> list[dict[str, Any]]:
    if hashlib.sha256(tree.read_bytes()).hexdigest() != TREE_SHA256:
        raise ValueError("JobBench tree differs from the audited official revision")
    return [
        x
        for x in json.loads(tree.read_text())
        if x["type"] == "file"
        and ("/task_folder/" in x["path"] or x["path"].endswith("/RUBRICS.json"))
    ]


def source_path(root: Path, relative: str) -> Path:
    path = (root / relative).resolve()
    if Path(relative).is_absolute() or not path.is_relative_to(root.resolve()):
        raise ValueError(f"Unsafe source path: {relative}")
    return path


def verify(data: bytes, entry: dict[str, Any]) -> None:
    if len(data) != entry["size"]:
        raise ValueError(f"size mismatch: {entry['path']}")
    if entry.get("lfs"):
        actual = hashlib.sha256(data).hexdigest()
        expected = entry["lfs"]["oid"]
    else:
        actual = hashlib.sha1(f"blob {len(data)}\0".encode() + data).hexdigest()
        expected = entry["oid"]
    if actual != expected:
        raise ValueError(f"content identity mismatch: {entry['path']}")


def fetch(entry: dict[str, Any], root: Path) -> dict[str, Any]:
    path = source_path(root, entry["path"])
    if path.exists():
        try:
            verify(path.read_bytes(), entry)
            return {"path": entry["path"], "status": "verified_cached"}
        except ValueError:
            pass
    url = f"https://huggingface.co/datasets/{REPOSITORY}/resolve/{REVISION}/"
    error = ""
    for _ in range(3):
        try:
            with urllib.request.urlopen(
                url + urllib.parse.quote(entry["path"]), timeout=30
            ) as response:
                data = response.read()
            verify(data, entry)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
            return {"path": entry["path"], "status": "downloaded_verified"}
        except Exception as exc:
            error = f"{type(exc).__name__}: {exc}"
    return {"path": entry["path"], "status": "blocked", "error": error}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tree", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    entries = json.loads(args.tree.read_text())
    selected = selected_entries(args.tree)
    # Mark existence of officially listed search directories, without downloading
    # answer materials. The adapter uses this only for network_required metadata.
    for x in entries:
        if x["type"] == "directory" and x["path"].endswith("/files_required_to_search"):
            source_path(args.output, x["path"]).mkdir(parents=True, exist_ok=True)
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(lambda entry: fetch(entry, args.output), selected))
    args.output.mkdir(parents=True, exist_ok=True)
    (args.output / "source-download.json").write_text(
        json.dumps(
            {
                "repository": REPOSITORY,
                "revision": REVISION,
                "tree_sha256": hashlib.sha256(args.tree.read_bytes()).hexdigest(),
                "input_bytes": sum(x["size"] for x in selected),
                "results": results,
            },
            indent=2,
        )
        + "\n"
    )
    errors = [x for x in results if x["status"] == "blocked"]
    print(f"verified {len(results) - len(errors)}/{len(results)} source files")
    if errors:
        raise SystemExit(f"{len(errors)} downloads blocked; see source-download.json")


if __name__ == "__main__":
    main()
