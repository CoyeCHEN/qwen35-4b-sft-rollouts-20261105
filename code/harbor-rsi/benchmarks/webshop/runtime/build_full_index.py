#!/usr/bin/env python3
"""Build a disk-backed official WebShop store and Lucene index."""

from __future__ import annotations

import argparse
from decimal import Decimal
import hashlib
import json
from pathlib import Path
import random
import re
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import zlib

import ijson


PRICE_RANGE = [10.0 * value for value in range(1, 100)]

REMOVED_KEYS = {
    "product_information",
    "brand",
    "brand_url",
    "list_price",
    "availability_quantity",
    "availability_status",
    "total_reviews",
    "total_answered_questions",
    "seller_id",
    "seller_name",
    "fulfilled_by_amazon",
    "fast_track_message",
    "aplus_present",
    "small_description_old",
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(8 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def normalize(
    product: dict, attributes: dict, human: dict
) -> tuple[dict, float] | None:
    asin = product["asin"]
    if asin == "nan" or len(asin) > 10:
        return None
    value = {key: item for key, item in product.items() if key not in REMOVED_KEYS}
    value["Title"] = product["name"]
    value["Description"] = product["full_description"]
    small = product["small_description"]
    value["BulletPoints"] = small if isinstance(small, list) else [small]
    value["Reviews"] = []
    value["Rating"] = "N.A."

    pricing = product.get("pricing")
    if not pricing:
        prices, price_tag = [100.0], "$100.0"
    else:
        prices = [
            float(Decimal(re.sub(r"[^\d.]", "", item)))
            for item in pricing.split("$")[1:]
        ]
        if len(prices) == 1:
            price_tag = f"${prices[0]}"
        else:
            price_tag = f"${prices[0]} to ${prices[1]}"
            prices = prices[:2]
    value["pricing"], value["Price"] = prices, price_tag
    price = prices[0] if len(prices) == 1 else random.uniform(*prices[:2])

    options, option_to_image = {}, {}
    for option_name, contents in (product.get("customization_options") or {}).items():
        if contents is None:
            continue
        option_values = []
        for content in contents:
            option = content["value"].strip().replace("/", " | ").lower()
            option_values.append(option)
            option_to_image[option] = content.get("image")
        options[option_name.lower()] = option_values
    value["options"] = options
    value["option_to_image"] = option_to_image
    value["Attributes"] = attributes.get(asin, {}).get("attributes", ["DUMMY_ATTR"])
    if asin in human:
        value["instructions"] = human[asin]
    images = product.get("images") or [""]
    value["MainImage"] = images[0]
    value["query"] = product["query"].lower().strip()

    # Keep only fields consumed by official rendering, goals, and reward code.
    keep = {
        "asin",
        "name",
        "category",
        "query",
        "product_category",
        "Title",
        "Description",
        "BulletPoints",
        "Reviews",
        "Rating",
        "pricing",
        "Price",
        "options",
        "option_to_image",
        "Attributes",
        "instructions",
        "MainImage",
    }
    return {key: value[key] for key in keep if key in value}, price


def document(product: dict) -> dict:
    option_text = ", and ".join(
        f"{name}: {', '.join(contents)}"
        for name, contents in product["options"].items()
    )
    contents = " ".join(
        [
            product["Title"],
            product["Description"],
            product["BulletPoints"][0],
            option_text,
        ]
    ).lower()
    return {"id": product["asin"], "contents": contents}


def human_goals(products: list[dict], prices: dict[str, float]) -> list[dict]:
    """Match WebShop's get_human_goals without importing its spaCy runtime."""
    goals = []
    skipped = 0
    for item in products:
        asin = item["asin"]
        for instruction in item.get("instructions", []):
            attributes = instruction["instruction_attributes"]
            if not attributes:
                skipped += 1
                continue

            price = prices[asin]
            candidates = [value for value in PRICE_RANGE if value > price][:4]
            if len(candidates) >= 2:
                _, price_upper = sorted(random.sample(candidates, 2))
                price_text = f", and price lower than {price_upper:.2f} dollars"
            else:
                price_upper = 1_000_000
                price_text = ""

            goals.append(
                {
                    "asin": asin,
                    "category": item["category"],
                    "query": item["query"],
                    "name": item["name"],
                    "product_category": item["product_category"],
                    "instruction_text": instruction["instruction"].strip(".")
                    + price_text,
                    "attributes": attributes,
                    "price_upper": price_upper,
                    "goal_options": instruction["instruction_options"],
                    "weight": 1,
                }
            )
    print(f"{skipped} skipped", flush=True)
    return goals


def directory_manifest(path: Path) -> list[dict[str, object]]:
    return [
        {
            "path": file.relative_to(path).as_posix(),
            "size": file.stat().st_size,
            "sha256": sha256(file),
        }
        for file in sorted(path.rglob("*"))
        if file.is_file()
    ]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--products", type=Path, required=True)
    parser.add_argument("--attributes", type=Path, required=True)
    parser.add_argument("--human", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--threads", type=int, default=1)
    parser.add_argument("--minimum-goals", type=int, default=500)
    parser.add_argument("--work-dir", type=Path)
    parser.add_argument("--anserini-jar", type=Path)
    parser.add_argument("--java", default="java")
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument("--resume", action="store_true")
    args = parser.parse_args()
    if args.output.exists() and any(args.output.iterdir()):
        if args.resume and (args.output / "products.sqlite").is_file():
            for stale in (args.output / "goals.json", args.output / "manifest.json"):
                stale.unlink(missing_ok=True)
            shutil.rmtree(args.output / "indexes", ignore_errors=True)
        elif not args.overwrite:
            raise SystemExit(f"{args.output} is not empty; pass --overwrite")
        else:
            shutil.rmtree(args.output)
    args.output.mkdir(parents=True, exist_ok=True)

    database_path = args.output / "products.sqlite"
    database = sqlite3.connect(database_path)
    goal_products, goal_prices = [], {}

    work_dir = args.work_dir or args.output
    work_dir.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(
        prefix="webshop-full-resources-", dir=work_dir
    ) as temporary:
        resources = Path(temporary) / "resources"
        resources.mkdir()
        docs = resources / "documents.jsonl"
        if args.resume:
            count = int(database.execute("SELECT count(*) FROM products").fetchone()[0])
            if count < 1_000_000:
                raise RuntimeError(
                    f"refusing to resume incomplete product store with {count} rows"
                )
            with docs.open("w", encoding="utf-8") as target:
                for position, (payload, price) in enumerate(
                    database.execute("SELECT payload, price FROM products"), start=1
                ):
                    product = json.loads(zlib.decompress(payload))
                    target.write(
                        json.dumps(document(product), ensure_ascii=False) + "\n"
                    )
                    if "instructions" in product:
                        goal_products.append(product)
                        goal_prices[product["asin"]] = float(price)
                    if position % 100000 == 0:
                        print(f"restored {position} indexed documents", flush=True)
        else:
            attributes = json.loads(args.attributes.read_text(encoding="utf-8"))
            human = json.loads(args.human.read_text(encoding="utf-8"))
            database.execute("PRAGMA journal_mode=OFF")
            database.execute("PRAGMA synchronous=OFF")
            database.execute("PRAGMA temp_store=MEMORY")
            database.execute(
                "CREATE TABLE products (asin TEXT PRIMARY KEY, payload BLOB NOT NULL, price REAL NOT NULL)"
            )
            seen, rows, count = set(), [], 0
            with (
                args.products.open("rb") as source,
                docs.open("w", encoding="utf-8") as target,
            ):
                for raw in ijson.items(source, "item"):
                    asin = raw.get("asin")
                    if asin in seen:
                        continue
                    converted = normalize(raw, attributes, human)
                    if converted is None:
                        continue
                    product, price = converted
                    seen.add(product["asin"])
                    payload = zlib.compress(
                        json.dumps(
                            product, ensure_ascii=False, separators=(",", ":")
                        ).encode("utf-8"),
                        level=3,
                    )
                    rows.append((product["asin"], payload, price))
                    target.write(
                        json.dumps(document(product), ensure_ascii=False) + "\n"
                    )
                    if "instructions" in product:
                        goal_products.append(product)
                        goal_prices[product["asin"]] = price
                    count += 1
                    if len(rows) >= 5000:
                        database.executemany(
                            "INSERT INTO products VALUES (?, ?, ?)", rows
                        )
                        database.commit()
                        rows.clear()
                    if count % 100000 == 0:
                        print(f"processed {count} products", flush=True)
            if rows:
                database.executemany("INSERT INTO products VALUES (?, ?, ?)", rows)
                database.commit()
        database.close()

        goals = human_goals(goal_products, goal_prices)
        random.seed(233)
        random.shuffle(goals)
        (args.output / "goals.json").write_text(
            json.dumps(goals, ensure_ascii=False, separators=(",", ":")),
            encoding="utf-8",
        )
        if len(goals) < args.minimum_goals:
            raise RuntimeError(
                f"asset build requires at least {args.minimum_goals} goals, found {len(goals)}"
            )

        index = args.output / "indexes"
        index_arguments = [
            "-collection",
            "JsonCollection",
            "-input",
            str(resources),
            "-index",
            str(index),
            "-generator",
            "DefaultLuceneDocumentGenerator",
            "-threads",
            str(args.threads),
            "-storePositions",
            "-storeDocvectors",
            "-storeRaw",
        ]
        if args.anserini_jar:
            command = [
                args.java,
                "-cp",
                str(args.anserini_jar),
                "io.anserini.index.IndexCollection",
                *index_arguments,
            ]
        else:
            command = [
                sys.executable,
                "-m",
                "pyserini.index.lucene",
                *(
                    argument if not argument.startswith("-") else f"-{argument}"
                    for argument in index_arguments
                ),
            ]
        subprocess.run(command, check=True)

    manifest = {
        "schema": "openharness.webshop.full-assets.v1",
        "product_set": "official-full-1.18m",
        "source_files": {
            args.products.name: {
                "size": args.products.stat().st_size,
                "sha256": sha256(args.products),
            },
            args.attributes.name: {
                "size": args.attributes.stat().st_size,
                "sha256": sha256(args.attributes),
            },
            args.human.name: {
                "size": args.human.stat().st_size,
                "sha256": sha256(args.human),
            },
        },
        "product_count": count,
        "goal_count": len(goals),
        "goal_order_seed": 233,
        "goal_generator": "official-get-human-goals-equivalent",
        "indexer": "anserini-0.14.3" if args.anserini_jar else "pyserini",
        "sqlite_sha256": sha256(args.output / "products.sqlite"),
        "goals_sha256": sha256(args.output / "goals.json"),
        "index_files": directory_manifest(index),
    }
    (args.output / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(
        json.dumps({"products": count, "goals": len(goals), "output": str(args.output)})
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
