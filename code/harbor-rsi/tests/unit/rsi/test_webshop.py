import json
import sys
import tomllib
from pathlib import Path

import pytest
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "benchmarks/webshop/src"))
from webshop_harbor.adapter import DEFAULT_IMAGE, FULL_SOURCE_HASHES, generate_dataset


def test_generate_webshop_smoke_dataset(tmp_path):
    manifest = generate_dataset(tmp_path, goal_indexes=[0, 7], max_steps=42)
    assert manifest["formal_official_score"] is False
    task = tmp_path / "small-goal-0007"
    config = tomllib.loads((task / "task.toml").read_text())
    assert config["metadata"]["goal_index"] == 7
    assert "at most 42 actions" in (task / "instruction.md").read_text()
    assert DEFAULT_IMAGE in (task / "environment/docker-compose.yaml").read_text()
    assert (task / "tests/webshop_verify.py").is_file()
    assert json.loads((tmp_path / "manifest.json").read_text()) == manifest


@pytest.mark.parametrize(
    "options", [{"goal_indexes": [-1]}, {"goal_indexes": [0], "max_steps": 0}]
)
def test_rejects_bad_limits(tmp_path, options):
    with pytest.raises(ValueError):
        generate_dataset(tmp_path, **options)


def test_full_assets_require_pinned_sources(tmp_path):
    assets = tmp_path / "assets"
    (assets / "indexes").mkdir(parents=True)
    (assets / "products.sqlite").touch()
    (assets / "goals.json").write_text("[]")
    data = {
        "product_set": "official-full-1.18m",
        "product_count": 1_180_000,
        "goal_count": 12_087,
        "source_files": {
            name: {"sha256": sha} for name, sha in FULL_SOURCE_HASHES.items()
        },
    }
    (assets / "manifest.json").write_text(json.dumps(data))
    manifest = generate_dataset(
        tmp_path / "tasks", goal_indexes=[499], product_set="full", full_root=assets
    )
    assert manifest["formal_official_score"] is True
    compose = yaml.safe_load(
        (tmp_path / "tasks/full-goal-0499/environment/docker-compose.yaml").read_text()
    )
    assert compose["services"]["webshop"]["volumes"][0]["source"] == str(assets)
    data["source_files"] = {}
    (assets / "manifest.json").write_text(json.dumps(data))
    with pytest.raises(ValueError, match="complete data"):
        generate_dataset(
            tmp_path / "invalid", goal_indexes=[0], product_set="full", full_root=assets
        )
