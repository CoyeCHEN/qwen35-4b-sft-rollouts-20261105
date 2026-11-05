"""Offline coverage of the example.com artifact check used by runtime fixtures."""

import subprocess
import sys
from pathlib import Path

import pytest


@pytest.mark.parametrize(
    ("html", "valid"),
    [
        (
            '<title>Example Domain</title><a href="https://iana.org/domains/example">More</a>',
            True,
        ),
        (
            "<!doctype html><html><title>Example Domain</title><p>Documentation examples.</p></html>",
            True,
        ),
        ("<html><title>Unrelated page</title></html>", False),
        ("", False),
    ],
    ids=[
        "previous-response",
        "current-response",
        "unrelated-response",
        "empty-response",
    ],
)
def test_example_artifact_validation(tmp_path: Path, html: str, valid: bool) -> None:
    verifier = (
        Path(__file__).resolve().parents[2]
        / "examples/tasks/network-policy-matrix/dynamic/shared-allowlist/tests/test.sh"
    ).read_text()
    # Execute the actual inline artifact validator, without its live network
    # probes or /logs writes. All runtime native reward assertions stay intact.
    code = verifier.split("elif ! python3 - <<'PY'\n", 1)[1].split("\nPY\n", 1)[0]
    code = code.replace('Path("/logs/artifacts/example.html")', "Path(sys.argv[1])")
    page = tmp_path / "example.html"
    page.write_text(html, encoding="utf-8")
    result = subprocess.run(
        [sys.executable, "-c", "import sys\n" + code, str(page)],
        capture_output=True,
        timeout=5,
        check=False,
    )
    assert (result.returncode == 0) is valid, result.stderr.decode(errors="replace")
