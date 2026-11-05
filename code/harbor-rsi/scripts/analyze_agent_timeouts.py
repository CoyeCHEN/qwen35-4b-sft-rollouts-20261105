"""Read the frozen campaign; write derived evidence without changing native logs."""

import argparse
import csv
import hashlib
import json
import re
import tomllib
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any


def redact(text: Any) -> str:
    return re.sub(r"sk-[A-Za-z0-9_-]{12,}", "[redacted]", str(text))


def text_content(message: dict[str, Any]) -> str:
    return "\n".join(
        str(c.get("text", ""))
        for c in message.get("content", [])
        if isinstance(c, dict) and c.get("type") == "text"
    )


def seconds(value: str) -> float:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()


def analyze(row: dict[str, str]) -> dict[str, Any]:
    trial = Path(row["result_path"]).parent
    result = json.loads((trial / "result.json").read_text())
    source = trial / "agent/open-harness.stdout.jsonl"
    events = []
    for line_number, line in enumerate(source.read_text().splitlines(), 1):
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        events.append((line_number, event))
    requests, tools, calls = [], [], {}
    current_timestamp = None
    last_assistant = None
    for line_number, event in events:
        message = event.get("message", {})
        if message.get("timestamp") is not None:
            current_timestamp = message["timestamp"]
        kind = event.get("type")
        if kind == "message_start" and message.get("role") == "assistant":
            requests.append(
                dict(
                    line=line_number,
                    timestamp_ms=message.get("timestamp"),
                    completed=False,
                    input_tokens=None,
                    output_tokens=None,
                    exact_duration_sec=None,
                )
            )
        elif kind == "message_end" and message.get("role") == "assistant":
            usage = message.get("usage", {})
            requests[-1].update(
                completed=True,
                input_tokens=usage.get("input", 0) + usage.get("cacheRead", 0),
                cached_tokens=usage.get("cacheRead", 0),
                output_tokens=usage.get("output", 0),
                stop_reason=message.get("stopReason"),
                text_excerpt=redact(text_content(message))[:700],
            )
            last_assistant = requests[-1]
        elif kind == "tool_execution_start":
            args = event.get("args", {})
            tool = dict(
                line=line_number,
                id=event.get("toolCallId"),
                name=event.get("toolName"),
                start_timestamp_ms=None,
                preceding_message_timestamp_ms=current_timestamp,
                end_timestamp_ms=None,
                exact_duration_sec=None,
                timeout_sec=args.get("timeout"),
                arguments_excerpt=redact(json.dumps(args, ensure_ascii=False))[:1000],
                arguments_sha256=hashlib.sha256(
                    json.dumps(args, sort_keys=True).encode()
                ).hexdigest(),
                ended=False,
            )
            tools.append(tool)
            calls[tool["id"]] = tool
        elif kind == "tool_execution_end" and event.get("toolCallId") in calls:
            tool = calls[event["toolCallId"]]
            details = event.get("result", {}).get("details", {})
            tool.update(
                ended=True,
                is_error=event.get("isError"),
                exit_code=details.get("exitCode"),
                reported_error=redact(details.get("error"))
                if details.get("error")
                else None,
                result_excerpt=redact(text_content(event.get("result", {})))[:1600],
            )
        if kind == "message_end" and message.get("role") == "toolResult":
            tool = calls.get(message.get("toolCallId"))
            if tool:
                tool["end_timestamp_ms"] = message.get("timestamp")
                before, end = (
                    tool["preceding_message_timestamp_ms"],
                    tool["end_timestamp_ms"],
                )
                tool["model_and_tool_interval_sec"] = (
                    (end - before) / 1000 if before is not None and end else None
                )
    for index, request in enumerate(requests):
        if index + 1 < len(requests) and request["timestamp_ms"] is not None:
            next_time = requests[index + 1]["timestamp_ms"]
            request["interval_to_next_request_sec"] = (
                (next_time - request["timestamp_ms"]) / 1000 if next_time else None
            )
    lifecycle = json.loads((trial / "agent/lifecycle.json").read_text())["lifecycle"]
    provider_path = next(trial.glob("remote-docker-*.jsonl"))
    provider = [json.loads(line) for line in provider_path.read_text().splitlines()]
    execution = result["agent_execution"]
    cancel = lifecycle["cancel_requested_at"]
    provider_execs = [
        {
            k: event.get(k)
            for k in ("time", "command_sha256", "exit_code", "duration_ms")
        }
        for event in provider
        if event.get("action") == "exec_completed"
    ]
    task = Path(result["task_id"]["path"])
    definition = tomllib.loads((task / "task.toml").read_text())
    marker = trial / "agent/open-harness.complete.json"
    verifier_sources = [p for p in (trial / "verifier").rglob("*") if p.is_file()]
    return dict(
        task_id=row["task_id"],
        benchmark=row["benchmark"],
        reward=float(row["reward"]),
        trial_path=str(trial),
        harbor_commit=row["harbor_commit"],
        harbor_wheel_sha256=row["harbor_wheel_sha256"],
        harbor_version="0.23.0+rsi.1",
        native_task_id=result["task_id"],
        native_task_name=result["task_name"],
        native_task_checksum=result["task_checksum"],
        native_agent_timeout_sec=definition["agent"]["timeout_sec"],
        completion_marker=json.loads(marker.read_text()) if marker.exists() else None,
        log_bytes=source.stat().st_size,
        agent_execution=execution,
        timeout_message=result["exception_info"]["exception_message"],
        controller_wall_seconds_to_cancel=cancel - seconds(execution["started_at"]),
        cleanup_wall_seconds=lifecycle["confirmed_at"] - cancel,
        cleanup_confirmed=lifecycle["cleanup_confirmed"],
        scopes=lifecycle["scopes"],
        verifier=result["verifier"],
        verifier_rewards=result["verifier_result"]["rewards"],
        verifier_exec_evidence=provider_execs[-1],
        verifier_stdout_tail=redact((trial / "verifier/test-stdout.txt").read_text())[
            -2200:
        ],
        judge_summary={
            k: v
            for k, v in json.loads(
                (trial / "verifier/jobbench_result.json").read_text()
            ).items()
            if not isinstance(v, (dict, list))
        }
        if (trial / "verifier/jobbench_result.json").exists()
        else None,
        infrastructure_errors=result["infrastructure_errors"],
        provider_last_action=provider[-1].get("action"),
        provider_execs=provider_execs,
        event_counts=dict(Counter(event.get("type") for _, event in events)),
        requests=requests,
        tools=tools,
        last_completed_assistant=last_assistant,
        extra_events=[
            {"line": line, **event}
            for line, event in events
            if event.get("type") in ("auto_retry_start", "auto_retry_end", "result")
        ],
        artifacts=[
            {"path": str(p.relative_to(trial)), "bytes": p.stat().st_size}
            for p in (trial / "artifacts").rglob("*")
            if p.is_file()
        ],
        source_hashes={
            str(p): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in (
                source,
                trial / "result.json",
                trial / "agent/lifecycle.json",
                provider_path,
                task / "task.toml",
                task / "instruction.md",
                task / "tests/test.sh",
                *verifier_sources,
                *([marker] if marker.exists() else []),
            )
        },
        timing_limits=(
            "Tool events have no own timestamps. Preceding message timestamp is a "
            "bound, not tool start; model_and_tool_interval includes generation. "
            "Request completion latency is absent. Controller and sandbox clocks "
            "are not calibrated; their timestamps must not establish exact deadlines."
        ),
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--campaign", type=Path, default=Path("artifacts/benchmark-reports/final-4x10")
    )
    parser.add_argument(
        "--output", type=Path, default=Path("docs/rsi/agent-timeout-evidence")
    )
    args = parser.parse_args()
    with (args.campaign / "cases.csv").open(newline="") as stream:
        rows = [r for r in csv.DictReader(stream) if r["status"] == "agent_failed"]
    if len(rows) != 6:
        raise ValueError("Expected the six frozen timeout cases")
    args.output.mkdir(parents=True, exist_ok=True)
    collected = []
    for row in rows:
        data = analyze(row)
        collected.append(data)
        name = row["task_id"].replace("/", "--")
        (args.output / f"{name}.json").write_text(
            redact(json.dumps(data, indent=2, ensure_ascii=False)) + "\n"
        )
        print(name, len(data["requests"]), len(data["tools"]))
    for field, columns in (
        (
            "requests",
            [
                "line",
                "timestamp_ms",
                "completed",
                "input_tokens",
                "cached_tokens",
                "output_tokens",
                "exact_duration_sec",
                "interval_to_next_request_sec",
            ],
        ),
        (
            "tools",
            [
                "line",
                "id",
                "name",
                "start_timestamp_ms",
                "preceding_message_timestamp_ms",
                "end_timestamp_ms",
                "ended",
                "timeout_sec",
                "exit_code",
                "is_error",
                "exact_duration_sec",
                "model_and_tool_interval_sec",
                "arguments_excerpt",
                "result_excerpt",
            ],
        ),
    ):
        with (args.output / f"{field}.csv").open("w", newline="") as stream:
            writer = csv.DictWriter(
                stream, fieldnames=["task_id", *columns], lineterminator="\n"
            )
            writer.writeheader()
            for data in collected:
                for item in data[field]:
                    writer.writerow(
                        {
                            "task_id": data["task_id"],
                            **{
                                c: json.dumps(item.get(c), ensure_ascii=False)
                                if c.endswith("_excerpt") and item.get(c) is not None
                                else item.get(c)
                                for c in columns
                            },
                        }
                    )


if __name__ == "__main__":
    main()
