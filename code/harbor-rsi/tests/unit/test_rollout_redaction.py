import hashlib
import builtins
import io
import json
import os
import stat
import sys
from pathlib import Path

import pytest

from harbor.extensions.rsi import trajectory
from harbor.extensions.rsi.trajectory import _lock_rollout, redact_rollout


def test_native_finalization_without_posix_lock_is_explicitly_unsupported(monkeypatch):
    original_import = builtins.__import__

    def without_fcntl(name, *args, **kwargs):
        if name == "fcntl":
            raise ImportError("POSIX lock unavailable")
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", without_fcntl)
    with pytest.raises(NotImplementedError, match="POSIX advisory file locking"):
        _lock_rollout(io.BytesIO())


@pytest.mark.skipif(sys.platform != "linux", reason="Exercises real directory fsync")
def test_directory_metadata_really_fsyncs_on_linux(tmp_path, monkeypatch):
    original_fsync = os.fsync
    flushed = []

    def sync_directory(fd):
        assert stat.S_ISDIR(os.fstat(fd).st_mode)
        original_fsync(fd)
        flushed.append(fd)

    monkeypatch.setattr(trajectory.os, "fsync", sync_directory)
    trajectory._sync_directory(tmp_path)
    assert len(flushed) == 1
    with pytest.raises(OSError):
        os.fstat(flushed[0])


def make_trace(path: Path, secret: str):
    path.mkdir()
    artifacts = path / "artifacts"
    artifacts.mkdir()

    def artifact(raw, encoding=None):
        ident = hashlib.sha256(raw).hexdigest()
        (artifacts / ident).write_bytes(raw)
        return {"$artifact": ident, "encoding": encoding, "size": len(raw)}

    parts = [
        b"utf8:\xe4",
        b"\xb8\xad " + secret[:7].encode(),
        secret[7:].encode() + b" end",
    ]
    records = []

    def event(kind, **data):
        records.append(dict(seq=len(records) + 1, timestamp=1, type=kind, data=data))

    event("run_start", run_id="r", task_input={"text": secret})
    event(
        "call_start",
        run_id="r",
        call_id="c",
        input={"prompt": secret},
        input_hash="old",
    )
    for part in parts:
        event(
            "tool_chunk",
            run_id="r",
            call_id="c",
            execution_id="t",
            chunk=artifact(part),
        )
    for part in [secret[:9], secret[9:]]:
        event(
            "call_chunk",
            run_id="r",
            call_id="c",
            chunk=json.dumps({"choices": [{"index": 0, "delta": {"content": part}}]}),
        )
        event(
            "call_event",
            run_id="r",
            call_id="c",
            event={"type": "text_delta", "delta": part},
        )
    event(
        "call_end", run_id="r", call_id="c", response={"content": secret}, status="stop"
    )
    event("run_end", run_id="r", status="completed")
    (path / "events.jsonl").write_text("".join(json.dumps(r) + "\n" for r in records))
    (path / "manifest.json").write_text(
        json.dumps({"schema_version": "open-harness-rollout-v2", "session_id": "s"})
    )


@pytest.mark.skipif(
    sys.platform != "linux", reason="Native POSIX rollout locking and atomic writeback"
)
def test_redaction_rebuilds_refs_and_masks_split_streams(tmp_path):
    secret = "synthetic-credential-value-12345"
    trace = tmp_path / "new-trace"
    make_trace(trace, secret)
    original = (trace / "events.jsonl").read_bytes()
    redact_rollout(trace, {secret})
    records = [json.loads(x) for x in (trace / "events.jsonl").read_text().splitlines()]
    refs = [r["data"]["chunk"] for r in records if r["type"] == "tool_chunk"]
    raw = []
    for ref in refs:
        data = (trace / "artifacts" / ref["$artifact"]).read_bytes()
        assert hashlib.sha256(data).hexdigest() == ref["$artifact"]
        assert len(data) == ref["size"]
        raw.append(data)
    assert b"".join(raw).decode() == "utf8:中 " + "*" * len(secret) + " end"
    chunks = [
        json.loads(r["data"]["chunk"])["choices"][0]["delta"]["content"]
        for r in records
        if r["type"] == "call_chunk"
    ]
    assert "".join(chunks) == "*" * len(secret)
    deltas = [r["data"]["event"]["delta"] for r in records if r["type"] == "call_event"]
    assert "".join(deltas) == "*" * len(secret)
    assert all(
        secret.encode() not in p.read_bytes() for p in trace.rglob("*") if p.is_file()
    )
    manifest = json.loads((trace / "manifest.json").read_text())
    assert (
        manifest["redaction"]["source_journal_sha256"]
        == hashlib.sha256(original).hexdigest()
    )
    assert [r["seq"] for r in records] == list(range(1, len(records) + 1))
    start = next(r["data"] for r in records if r["type"] == "call_start")
    assert (
        start["input_hash"]
        == hashlib.sha256(
            json.dumps(start["input"], sort_keys=True, ensure_ascii=False).encode()
        ).hexdigest()
    )


@pytest.mark.skipif(
    sys.platform != "linux", reason="Native POSIX rollout lock precedes artifact checks"
)
def test_corrupt_artifact_rejected_before_any_mutation(tmp_path):
    trace = tmp_path / "new-trace"
    make_trace(trace, "synthetic-secret")
    next((trace / "artifacts").iterdir()).write_bytes(b"corrupt")
    before = {p: p.read_bytes() for p in trace.rglob("*") if p.is_file()}
    with pytest.raises(ValueError, match="corrupt"):
        redact_rollout(trace, {"synthetic-secret"})
    assert all(p.read_bytes() == value for p, value in before.items())


@pytest.mark.skipif(
    sys.platform != "linux", reason="Native POSIX rollout locking and atomic writeback"
)
def test_background_output_split_secret_is_masked_and_addressed(tmp_path):
    secret = "synthetic-background-credential-67890"
    trace = tmp_path / "new-trace"
    make_trace(trace, secret)
    journal = trace / "events.jsonl"
    records = [json.loads(line) for line in journal.read_text().splitlines()]
    for event in records:
        if event["type"] == "tool_chunk":
            event["type"] = "context_event"
            event["data"] = dict(
                run_id="r",
                event=dict(
                    type="background_job_output",
                    job_id="j",
                    chunk=event["data"]["chunk"],
                ),
            )
    journal.write_text("".join(json.dumps(event) + "\n" for event in records))
    redact_rollout(trace, {secret})
    records = [json.loads(line) for line in journal.read_text().splitlines()]
    raw = []
    for event in records:
        if event["type"] != "context_event":
            continue
        ref = event["data"]["event"]["chunk"]
        data = (trace / "artifacts" / ref["$artifact"]).read_bytes()
        assert hashlib.sha256(data).hexdigest() == ref["$artifact"]
        assert len(data) == ref["size"]
        raw.append(data)
    assert b"".join(raw).decode() == "utf8:中 " + "*" * len(secret) + " end"


@pytest.mark.parametrize("middle", ["ABCDEFGHIJ", "中文甲乙丙丁"])
@pytest.mark.skipif(
    sys.platform != "linux", reason="Native POSIX rollout locking and atomic writeback"
)
def test_shared_json_artifact_preserves_masks_from_every_stream(tmp_path, middle):
    trace = tmp_path / "new-trace"
    trace.mkdir()
    artifacts = trace / "artifacts"
    artifacts.mkdir()

    def chunk(text):
        return json.dumps(
            {"choices": [{"index": 0, "delta": {"content": text}}]},
            ensure_ascii=False,
            separators=(",", ":"),
        )

    raw = chunk(middle).encode()
    ident = hashlib.sha256(raw).hexdigest()
    (artifacts / ident).write_bytes(raw)
    ref = {"$artifact": ident, "encoding": "utf-8", "size": len(raw)}
    records = [
        dict(
            seq=i + 1,
            timestamp=1,
            type="call_chunk",
            data=dict(call_id=call, chunk=part),
        )
        for i, (call, part) in enumerate(
            [("c1", chunk("xxx")), ("c1", ref), ("c2", ref), ("c2", chunk("yyy"))]
        )
    ]
    (trace / "events.jsonl").write_text("".join(json.dumps(e) + "\n" for e in records))
    (trace / "manifest.json").write_text(
        json.dumps({"schema_version": "open-harness-rollout-v2", "session_id": "s"})
    )
    split = len(middle) // 2
    redact_rollout(trace, {"xxx" + middle[:split], middle[split:] + "yyy"})
    events = [
        json.loads(line) for line in (trace / "events.jsonl").read_text().splitlines()
    ]
    for event in [events[1], events[2]]:
        reference = event["data"]["chunk"]
        data = (artifacts / reference["$artifact"]).read_bytes()
        assert hashlib.sha256(data).hexdigest() == reference["$artifact"]
        assert len(data) == reference["size"]
        assert json.loads(data)["choices"][0]["delta"]["content"] == "*" * len(middle)


@pytest.mark.skipif(sys.platform != "linux", reason="Exercises native POSIX flock")
def test_active_writer_rejected_and_other_trace_untouched(tmp_path):
    import fcntl

    active, historical = tmp_path / "active", tmp_path / "historical"
    for directory in (active, historical):
        make_trace(directory, "synthetic-credential")
    before = {p: p.read_bytes() for p in historical.rglob("*") if p.is_file()}
    with (active / "events.jsonl").open("rb") as writer:
        fcntl.flock(writer.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        with pytest.raises(BlockingIOError):
            redact_rollout(active, {"synthetic-credential"})
    redact_rollout(active, {"synthetic-credential"})
    assert all(p.read_bytes() == value for p, value in before.items())


@pytest.mark.skipif(
    sys.platform != "linux",
    reason="Native POSIX rollout finalization and atomic writeback",
)
def test_adapter_redaction_then_core_scrub_preserves_hashes_and_covers_logs(tmp_path):
    from types import SimpleNamespace
    from harbor.agents.installed.open_harness import OpenHarnessAgent
    from harbor.models.agent.context import AgentContext
    from harbor.trial.single_step import SingleStepTrial

    secret = "synthetic-credential"
    logs = tmp_path / "agent"
    logs.mkdir()
    trace = logs / "openharness-rollout"
    make_trace(trace, secret)
    background = trace / "background-jobs"
    background.mkdir()
    (background / "job.log").write_text(secret)
    (trace / "tool-results").mkdir()
    (trace / "tool-results/result.txt").write_text(secret)
    agent = OpenHarnessAgent(
        logs_dir=logs,
        model_name="deepseek/deepseek-flash",
        wheel_path=str(tmp_path / "candidate.whl"),
        extra_env={"DEEPSEEK_API_KEY": secret},
    )
    agent.populate_context_post_run(AgentContext())
    snapshot = {p: p.read_bytes() for p in (trace / "artifacts").iterdir()}
    trial = object.__new__(SingleStepTrial)
    trial.__dict__.update(
        agent=agent,
        user_agent=None,
        task=SimpleNamespace(config=SimpleNamespace(verifier=SimpleNamespace(env={}))),
        config=SimpleNamespace(verifier=SimpleNamespace(env={})),
        paths=SimpleNamespace(trial_dir=tmp_path),
    )
    trial._scrub_jobs_dir()
    assert all(p.read_bytes() == data for p, data in snapshot.items())
    assert all(hashlib.sha256(p.read_bytes()).hexdigest() == p.name for p in snapshot)
    assert all(
        secret.encode() not in p.read_bytes() for p in trace.rglob("*") if p.is_file()
    )
