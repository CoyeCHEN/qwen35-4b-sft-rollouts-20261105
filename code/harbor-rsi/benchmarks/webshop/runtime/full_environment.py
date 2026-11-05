"""Memory-bounded facade over the official full WebShop environment."""

from __future__ import annotations

from collections.abc import Mapping
import json
from pathlib import Path
import sqlite3
import zlib

import numpy as np


class ProductStore(Mapping):
    def __init__(self, path: Path):
        self.database = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
        self.cache: dict[str, tuple[dict, float]] = {}

    def _load(self, asin: str) -> tuple[dict, float]:
        asin = asin.upper()
        if asin not in self.cache:
            row = self.database.execute(
                "SELECT payload, price FROM products WHERE asin = ?", (asin,)
            ).fetchone()
            if row is None:
                raise KeyError(asin)
            self.cache[asin] = (json.loads(zlib.decompress(row[0])), float(row[1]))
            if len(self.cache) > 500:
                self.cache.pop(next(iter(self.cache)))
        return self.cache[asin]

    def __getitem__(self, asin: str) -> dict:
        return self._load(asin)[0]

    def price(self, asin: str) -> float:
        return self._load(asin)[1]

    def __iter__(self):
        for row in self.database.execute("SELECT asin FROM products"):
            yield row[0]

    def __len__(self) -> int:
        return int(self.database.execute("SELECT count(*) FROM products").fetchone()[0])


class ProductPrices(Mapping):
    def __init__(self, products: ProductStore):
        self.products = products

    def __getitem__(self, asin: str) -> float:
        return self.products.price(asin)

    def get(self, asin: str, default=None):
        try:
            return self[asin]
        except KeyError:
            return default

    def __iter__(self):
        return iter(self.products)

    def __len__(self) -> int:
        return len(self.products)


def create_full_environment(root: Path):
    from pyserini.search.lucene import LuceneSearcher
    import web_agent_site.envs.web_agent_text_env as text_env

    products = ProductStore(root / "products.sqlite")
    searcher = LuceneSearcher(str(root / "indexes"))
    goals = json.loads((root / "goals.json").read_text(encoding="utf-8"))

    def full_search(
        keywords,
        search_engine,
        all_products,
        product_item_dict,
        attribute_to_asins=None,
    ):
        if keywords and keywords[0] in {"<r>", "<a>", "<c>", "<q>"}:
            return text_env.get_top_n_product_from_keywords_original(
                keywords,
                search_engine,
                all_products,
                product_item_dict,
                attribute_to_asins,
            )
        hits = search_engine.search(" ".join(keywords), k=50)
        result = []
        for hit in hits:
            asin = json.loads(search_engine.doc(hit.docid).raw())["id"]
            try:
                result.append(products[asin])
            except KeyError:
                continue
        return result

    if not hasattr(text_env, "get_top_n_product_from_keywords_original"):
        text_env.get_top_n_product_from_keywords_original = (
            text_env.get_top_n_product_from_keywords
        )
    text_env.get_top_n_product_from_keywords = full_search

    server = text_env.SimServer.__new__(text_env.SimServer)
    server.base_url = "http://127.0.0.1:3000"
    server.all_products = []
    server.product_item_dict = products
    server.product_prices = ProductPrices(products)
    server.search_engine = searcher
    server.goals = goals
    server.show_attrs = False
    server.weights = [goal["weight"] for goal in goals]
    server.cum_weights = [0] + np.cumsum(server.weights).tolist()
    server.user_sessions = {}
    server.search_time = 0
    server.render_time = 0
    server.sample_time = 0
    server.assigned_instruction_text = None
    return text_env.WebAgentTextEnv(observation_mode="text", server=server)
