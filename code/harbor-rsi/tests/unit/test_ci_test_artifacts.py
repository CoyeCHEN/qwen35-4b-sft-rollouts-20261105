import importlib.util
from pathlib import Path
from zipfile import ZipFile

import pytest

spec = importlib.util.spec_from_file_location(
    "ci_test_artifacts",
    Path(__file__).resolve().parents[2] / "scripts/collect_ci_test_artifacts.py",
)
assert spec is not None and spec.loader is not None
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
collect = module.collect


def test_collect_preserves_trial_and_junit_evidence_without_copying_environment(
    tmp_path,
):
    root = tmp_path / "pytest"
    trial = root / "case/trials/trial-1"
    for path in (
        trial / "verifier/stdout.txt",
        trial / "agent/trajectory.json",
        trial / "result.json",
        trial / "fixture-root/private.txt",
    ):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("fixture evidence")
    report = tmp_path / "unit-results.xml"
    report.write_text("<testsuites/>")
    target = tmp_path / "evidence.zip"
    assert collect(root, target, [report]) == 4
    with ZipFile(target) as archive:
        assert set(archive.namelist()) == {
            "unit-results.xml",
            "trials/case/trials/trial-1/result.json",
            "trials/case/trials/trial-1/agent/trajectory.json",
            "trials/case/trials/trial-1/verifier/stdout.txt",
        }


def test_collect_does_not_follow_cyclic_or_external_links(tmp_path):
    root = tmp_path / "pytest"
    trial = root / "case/trials/trial-1"
    trial.mkdir(parents=True)
    outside = tmp_path / "outside.txt"
    outside.write_text("must not be collected")
    try:
        (root / "loop").symlink_to(root, target_is_directory=True)
        (trial / "result.json").symlink_to(outside)
    except OSError:
        pytest.skip("Host does not permit creating symlinks")
    target = tmp_path / "evidence.zip"
    assert collect(root, target, []) == 0
    with ZipFile(target) as archive:
        assert not archive.namelist()
