"""Generate Harbor tasks backed by the official WebShop text environment."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent
TEMPLATE = ROOT / "task-template"

OFFICIAL_REPOSITORY = "https://github.com/princeton-nlp/WebShop"
OFFICIAL_COMMIT = "64fa2a5c15c7daa698b9ac93f5bb5437b634c9bd"
DEFAULT_IMAGE = f"openharness-webshop:small-{OFFICIAL_COMMIT[:7]}"
DEFAULT_GOALS = (0,)
PRODUCT_SETS = {
    "small": {
        "label": "official-small-1000",
        "formal": False,
        "prefix": "small-goal",
    },
    "full": {
        "label": "official-full-1.18m",
        "formal": True,
        "prefix": "full-goal",
    },
}
FULL_SOURCE_HASHES = {
    "items_shuffle.json": "2ef591d65df3af89e972ab72468eb82cbf124d876552d9f3678667edd620a6c8",
    "items_ins_v2.json": "1d36af476bdb8f82a5da62bd8acdabe54cd8de2fa84010d37da5c4890feb447e",
}


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _render(source: Path, target: Path, replacements: dict[str, str]) -> None:
    text = source.read_text(encoding="utf-8")
    for old, new in replacements.items():
        text = text.replace(old, new)
    if "__" in text:
        unresolved = sorted({part for part in text.split() if part.startswith("__")})
        if unresolved:
            raise ValueError(
                f"unresolved template placeholders in {source}: {unresolved}"
            )
    target.write_text(text, encoding="utf-8")


def generate_task(
    output_root: Path,
    *,
    goal_index: int,
    image: str,
    max_steps: int,
    overwrite: bool,
    product_set: str = "small",
    full_root: Path | None = None,
) -> dict[str, object]:
    if goal_index < 0:
        raise ValueError("goal indexes must be non-negative")
    if max_steps <= 0:
        raise ValueError("max_steps must be positive")

    spec = PRODUCT_SETS[product_set]
    if product_set == "full":
        if full_root is None or not full_root.is_absolute():
            raise ValueError("full product set requires an absolute --full-root")
        required = (
            full_root / "products.sqlite",
            full_root / "goals.json",
            full_root / "indexes",
            full_root / "manifest.json",
        )
        missing = [str(path) for path in required if not path.exists()]
        if missing:
            raise FileNotFoundError(f"full WebShop assets are incomplete: {missing}")
        assets = json.loads((full_root / "manifest.json").read_text(encoding="utf-8"))
        sources = assets.get("source_files") or {}
        source_hashes = {
            name: (sources.get(name) or {}).get("sha256") for name in FULL_SOURCE_HASHES
        }
        if (
            assets.get("product_set") != "official-full-1.18m"
            or int(assets.get("product_count", 0)) < 1_000_000
            or int(assets.get("goal_count", 0)) < 500
            or source_hashes != FULL_SOURCE_HASHES
        ):
            raise ValueError(
                "full WebShop asset manifest does not prove the official complete data"
            )
    name = f"{spec['prefix']}-{goal_index:04d}"
    target = output_root / name
    if target.exists():
        if not overwrite:
            raise FileExistsError(f"{target} exists; pass --overwrite")
        shutil.rmtree(target)

    environment = target / "environment"
    tests = target / "tests"
    solution = target / "solution"
    environment.mkdir(parents=True)
    tests.mkdir()
    solution.mkdir()

    volumes = ""
    if full_root is not None:
        volumes = "\n".join(
            [
                "    volumes:",
                "      - type: bind",
                f"        source: {json.dumps(str(full_root))}",
                "        target: /opt/webshop/full",
                "        read_only: true",
            ]
        )
    replacements = {
        "__TASK_NAME__": json.dumps(f"webshop/{name}"),
        "__GOAL_INDEX__": str(goal_index),
        "__WEBSHOP_IMAGE__": image,
        "__MAX_STEPS__": str(max_steps),
        "__OFFICIAL_COMMIT__": OFFICIAL_COMMIT,
        "__PRODUCT_SET__": str(spec["label"]),
        "__FORMAL_OFFICIAL_SCORE__": str(spec["formal"]).lower(),
        "__WEBSHOP_VOLUMES__": volumes,
    }
    _render(TEMPLATE / "instruction.md", target / "instruction.md", replacements)
    _render(TEMPLATE / "task.toml", target / "task.toml", replacements)
    _render(
        TEMPLATE / "environment" / "docker-compose.yaml",
        environment / "docker-compose.yaml",
        replacements,
    )
    shutil.copy2(TEMPLATE / "environment" / "Dockerfile", environment / "Dockerfile")
    shutil.copy2(TEMPLATE / "environment" / "webshop.py", environment / "webshop.py")
    shutil.copy2(TEMPLATE / "tests" / "test.sh", tests / "test.sh")
    shutil.copy2(TEMPLATE / "tests" / "webshop_verify.py", tests / "webshop_verify.py")
    shutil.copy2(TEMPLATE / "solution" / "solve.sh", solution / "solve.sh")
    (tests / "test.sh").chmod(0o755)
    (solution / "solve.sh").chmod(0o755)

    return {
        "name": name,
        "goal_index": goal_index,
        "product_set": spec["label"],
        "formal_official_score": spec["formal"],
        "official_repository": OFFICIAL_REPOSITORY,
        "official_commit": OFFICIAL_COMMIT,
        "image": image,
        "max_steps": max_steps,
        "instruction_sha256": _sha256(target / "instruction.md"),
        "task_toml_sha256": _sha256(target / "task.toml"),
    }


def generate_dataset(
    output_root: Path,
    *,
    goal_indexes: list[int],
    image: str = DEFAULT_IMAGE,
    max_steps: int = 100,
    overwrite: bool = False,
    product_set: str = "small",
    full_root: Path | None = None,
) -> dict[str, object]:
    if product_set not in PRODUCT_SETS:
        raise ValueError(f"unknown product set: {product_set}")
    output_root.mkdir(parents=True, exist_ok=True)
    tasks = [
        generate_task(
            output_root,
            goal_index=index,
            image=image,
            max_steps=max_steps,
            overwrite=overwrite,
            product_set=product_set,
            full_root=full_root,
        )
        for index in goal_indexes
    ]
    manifest = {
        "schema": "openharness.webshop.harbor.v1",
        "official_repository": OFFICIAL_REPOSITORY,
        "official_commit": OFFICIAL_COMMIT,
        "product_set": PRODUCT_SETS[product_set]["label"],
        "formal_official_score": PRODUCT_SETS[product_set]["formal"],
        "image": image,
        "tasks": tasks,
    }
    if full_root is not None:
        manifest["full_asset_root"] = str(full_root)
        manifest["full_asset_manifest"] = json.loads(
            (full_root / "manifest.json").read_text(encoding="utf-8")
        )
    (output_root / "manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    return manifest


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--goal-index", action="append", type=int, dest="goal_indexes")
    parser.add_argument("--image", default=DEFAULT_IMAGE)
    parser.add_argument("--max-steps", type=int, default=100)
    parser.add_argument("--product-set", choices=sorted(PRODUCT_SETS), default="small")
    parser.add_argument("--full-root", type=Path)
    parser.add_argument("--overwrite", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    manifest = generate_dataset(
        args.output_root,
        goal_indexes=args.goal_indexes or list(DEFAULT_GOALS),
        image=args.image,
        max_steps=args.max_steps,
        overwrite=args.overwrite,
        product_set=args.product_set,
        full_root=args.full_root,
    )
    print(
        f"generated {len(manifest['tasks'])} WebShop task(s) under {args.output_root}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
