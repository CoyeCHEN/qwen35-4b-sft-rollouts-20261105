"""The no-model egress fixture must use HEAD and retain failed requests."""

import json
from unittest.mock import MagicMock

import pytest

from benchmarks.readiness.network_fixture import EgressOptions, probe_program


@pytest.mark.parametrize(
    "urls",
    [
        [],
        ["https://example.org"] * 9,
        ["http://example.org"],
        ["https://user:secret@example.org"],
        ["https://example.org?token=secret"],
        ["https://example.org:2375"],
        ["https://example.org/#fragment"],
    ],
)
def test_reject_undeclared_or_credential_bearing_requests(urls: list[str]) -> None:
    with pytest.raises(ValueError):
        probe_program(urls)


def test_actual_probe_only_reads_headers_and_records_failure(
    monkeypatch, capsys
) -> None:
    calls = []
    response = MagicMock()
    response.__enter__.return_value.status = 200

    def urlopen(request, *, timeout):
        calls.append((request.full_url, request.get_method(), timeout))
        if request.full_url.endswith("/unavailable"):
            raise TimeoutError("bounded failure")
        return response

    monkeypatch.setattr("urllib.request.urlopen", urlopen)
    urls = ["https://example.org/config.json", "https://example.org/unavailable"]
    exec(compile(probe_program(urls), "readonly-probe", "exec"), {})
    assert calls == [(url, "HEAD", 5) for url in urls]
    assert json.loads(capsys.readouterr().out) == [
        {"requested_url": urls[0], "status": 200},
        {"requested_url": urls[1], "exception": "TimeoutError"},
    ]
    response.__enter__.return_value.read.assert_not_called()


def test_native_options_accept_probe_without_changing_actor_settings() -> None:
    options = EgressOptions.model_validate(
        {"wheel_path": "/fixture.whl", "probe_urls": ["https://example.org/config"]}
    )
    assert options.probe_urls == ["https://example.org/config"]
    with pytest.raises(ValueError):
        EgressOptions.model_validate(
            {"wheel_path": "/fixture.whl", "probe_urls": ["http://example.org/config"]}
        )
