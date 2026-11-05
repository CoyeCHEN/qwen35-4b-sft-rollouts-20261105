"""Convert Open Harness JSONL events to Harbor ATIF-v1.7."""

from __future__ import annotations

import json
import hashlib
import os
from collections.abc import Iterable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, BinaryIO


def _lock_rollout(file: BinaryIO) -> None:
    try:
        import fcntl
    except ImportError as error:
        raise NotImplementedError(
            "Rollout finalization requires POSIX advisory file locking"
        ) from error
    fcntl.flock(file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)


def _sync_directory(path: Path) -> None:
    """Persist directory metadata on the supported POSIX execution backend."""
    fd = os.open(path, os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def redact_rollout(directory: Path, secrets: set[str]) -> None:
    """Redact a closed, newly collected rollout and rebuild its artifact refs.

    This is an evidence transformation, not a reader for old Harness versions.
    Only Trial finalization calls it; never point it at historical results.
    """
    journal = directory / "events.jsonl"
    with journal.open("rb") as lock:
        _lock_rollout(lock)
        raw = lock.read()
        manifest_path = directory / "manifest.json"
        manifest = json.loads(manifest_path.read_bytes())
        if manifest.get("schema_version") != "open-harness-rollout-v2":
            raise ValueError("Unsupported rollout schema for redaction")
        records = [json.loads(line) for line in raw.splitlines()]
        artifacts = directory / "artifacts"
        original = {p.name: p.read_bytes() for p in artifacts.glob("*") if p.is_file()}
        for ident, data in original.items():
            if hashlib.sha256(data).hexdigest() != ident:
                raise ValueError("Cannot redact a corrupt rollout artifact")
        changed = dict(original)
        ordered = sorted(secrets, key=len, reverse=True)

        def mask(parts):
            joined = (
                b"".join(parts)
                if parts and isinstance(parts[0], bytes)
                else "".join(parts)
            )
            for secret in ordered:
                if isinstance(joined, bytes):
                    joined = joined.replace(
                        secret.encode(), b"*" * len(secret.encode())
                    )
                else:
                    joined = joined.replace(secret, "*" * len(secret))
            result, offset = [], 0
            for part in parts:
                result.append(joined[offset : offset + len(part)])
                offset += len(part)
            return result

        def resolve(value):
            if isinstance(value, dict) and set(value) == {
                "$artifact",
                "encoding",
                "size",
            }:
                data = original[value["$artifact"]]
                if len(data) != value["size"]:
                    raise ValueError("Corrupt rollout artifact size")
                return data.decode() if value["encoding"] == "utf-8" else data
            return value

        def update(container, key, value):
            old = container[key]
            if isinstance(old, dict) and "$artifact" in old:
                ident = old["$artifact"]
                if isinstance(value, str):
                    value = "".join(
                        a if a != b else c
                        for a, b, c in zip(
                            changed[ident].decode(),
                            original[ident].decode(),
                            value,
                            strict=True,
                        )
                    )
                    changed[ident] = value.encode()
                else:
                    changed[ident] = bytes(
                        a if a != b else c
                        for a, b, c in zip(
                            changed[ident], original[ident], value, strict=True
                        )
                    )
            else:
                container[key] = value

        def merge_json_masks(source, previous, current):
            # Reused content-addressed JSON can be redacted in multiple streams.
            # Merge string positions, independent of serialization whitespace.
            if isinstance(source, str):
                return "".join(
                    a if a != b else c
                    for a, b, c in zip(previous, source, current, strict=True)
                )
            if isinstance(source, dict):
                return {
                    k: merge_json_masks(v, previous[k], current[k])
                    for k, v in source.items()
                }
            if isinstance(source, list):
                return [
                    merge_json_masks(s, p, c)
                    for s, p, c in zip(source, previous, current, strict=True)
                ]
            return current

        streams: dict[tuple[Any, ...], list[tuple[dict[str, Any], str, Any]]] = {}
        for event in records:
            if (
                event["type"] == "context_event"
                and event["data"].get("event", {}).get("type")
                == "background_job_output"
            ):
                data = event["data"]["event"]
                streams.setdefault(
                    ("tool_chunk", data["job_id"], "background"), []
                ).append((data, "chunk", resolve(data["chunk"])))
                continue
            if event["type"] in {"tool_chunk", "call_chunk", "call_event"}:
                data = event["data"]
                identity = (
                    data.get("execution_id")
                    if event["type"] == "tool_chunk"
                    else data.get("call_id")
                )
                key = "event" if event["type"] == "call_event" else "chunk"
                subtype = data[key].get("type") if key == "event" else None
                streams.setdefault((event["type"], identity, subtype), []).append(
                    (data, key, resolve(data[key]))
                )
        for (kind, _, _), chunks in streams.items():
            if kind == "tool_chunk":
                for (container, key, _), value in zip(
                    chunks, mask([x[2] for x in chunks])
                ):
                    update(container, key, value)
                continue
            # Provider chunks are JSON strings. Redact split string values at
            # the same JSON path, keeping tool/choice indices and chunk order.
            parsed, fields, decoded_artifacts = [], {}, {}

            def leaves(value, path=()):
                if isinstance(value, dict):
                    for key, child in value.items():
                        child = resolve(child)
                        if isinstance(child, str):
                            fields.setdefault(path + (key,), []).append(
                                (value, key, child)
                            )
                        else:
                            leaves(child, path + (key,))
                elif isinstance(value, list):
                    for index, child in enumerate(value):
                        leaves(
                            child,
                            path
                            + (
                                (
                                    child.get("index", index)
                                    if isinstance(child, dict)
                                    else index
                                ),
                            ),
                        )

            for container, key, value in chunks:
                try:
                    if kind == "call_event":
                        decoded = value
                    elif isinstance(container[key], dict):
                        ident = container[key]["$artifact"]
                        if ident not in decoded_artifacts:
                            decoded_artifacts[ident] = json.loads(value)
                        decoded = decoded_artifacts[ident]
                    else:
                        decoded = json.loads(value)
                except (ValueError, UnicodeDecodeError):
                    continue
                parsed.append((container, key, decoded))
                leaves(decoded)
            for parts in fields.values():
                for (container, key, _), value in zip(
                    parts, mask([x[2] for x in parts])
                ):
                    update(container, key, value)
            for container, key, decoded in parsed:
                if kind == "call_event":
                    continue
                source = json.loads(resolve(container[key]))
                if isinstance(container[key], dict):
                    ident = container[key]["$artifact"]
                    decoded = merge_json_masks(
                        source, json.loads(changed[ident]), decoded
                    )
                    if source != decoded:
                        changed[ident] = json.dumps(
                            decoded, ensure_ascii=False
                        ).encode()
                elif source != decoded:
                    update(container, key, json.dumps(decoded, ensure_ascii=False))

        for ident, data in changed.items():
            changed[ident] = mask([data])[0]

        def scrub(value):
            if isinstance(value, dict):
                if set(value) == {"$artifact", "encoding", "size"}:
                    resolve(value)
                    data = changed[value["$artifact"]]
                    return dict(
                        value,
                        **{
                            "$artifact": hashlib.sha256(data).hexdigest(),
                            "size": len(data),
                        },
                    )
                return {key: scrub(child) for key, child in value.items()}
            if isinstance(value, list):
                return [scrub(child) for child in value]
            return mask([value])[0] if isinstance(value, str) else value

        records, manifest = scrub(records), scrub(manifest)
        by_hash = {hashlib.sha256(data).hexdigest(): data for data in changed.values()}

        def unpack(value):
            if isinstance(value, dict):
                if set(value) == {"$artifact", "encoding", "size"}:
                    data = by_hash[value["$artifact"]]
                    return data.decode() if value["encoding"] == "utf-8" else data
                return {key: unpack(child) for key, child in value.items()}
            if isinstance(value, list):
                return [unpack(child) for child in value]
            return value

        for event in records:
            if event["type"] == "call_start" and "input_hash" in event["data"]:
                event["data"]["input_hash"] = hashlib.sha256(
                    json.dumps(
                        unpack(event["data"]["input"]),
                        sort_keys=True,
                        ensure_ascii=False,
                    ).encode()
                ).hexdigest()
        manifest["redaction"] = dict(
            source_journal_sha256=hashlib.sha256(raw).hexdigest(),
            replacement="same-width asterisks",
            stream_boundaries_preserved=True,
        )

        def atomic(path, data):
            temporary = path.with_name(path.name + ".redacting")
            with temporary.open("xb") as output:
                os.chmod(temporary, 0o600)
                output.write(data)
                output.flush()
                os.fsync(output.fileno())
            os.replace(temporary, path)

        for old, data in changed.items():
            ident = hashlib.sha256(data).hexdigest()
            if old != ident and not (artifacts / ident).exists():
                atomic(artifacts / ident, data)
        if artifacts.exists():
            _sync_directory(artifacts)
        atomic(
            journal,
            b"".join(
                json.dumps(e, ensure_ascii=False, sort_keys=True).encode() + b"\n"
                for e in records
            ),
        )
        atomic(
            manifest_path,
            json.dumps(manifest, ensure_ascii=False, sort_keys=True).encode(),
        )
        _sync_directory(directory)
        for old, data in changed.items():
            if hashlib.sha256(data).hexdigest() != old:
                (artifacts / old).unlink()
        if artifacts.exists():
            _sync_directory(artifacts)


def _number(value, default=0):
    return (
        value
        if isinstance(value, (int, float)) and not isinstance(value, bool)
        else default
    )


def _timestamp(value):
    if not isinstance(value, (int, float)):
        return None
    return (
        datetime.fromtimestamp(value / 1000, tz=UTC).isoformat().replace("+00:00", "Z")
    )


def _content_text(content):
    if isinstance(content, str):
        return content
    if not isinstance(content, list):
        return (
            ""
            if content is None
            else json.dumps(content, ensure_ascii=False, sort_keys=True)
        )
    parts = []
    for item in content:
        if not isinstance(item, dict):
            parts.append(json.dumps(item, ensure_ascii=False, sort_keys=True))
        elif item.get("type") == "text":
            parts.append(str(item.get("text", "")))
        elif item.get("type") == "image":
            parts.append(f"[image: {item.get('mimeType', 'unknown')}]")
    return "\n".join(part for part in parts if part)


def _assistant_parts(message):
    text, reasoning, calls = [], [], []
    for item in message.get("content") or []:
        if not isinstance(item, dict):
            continue
        if item.get("type") == "text":
            text.append(str(item.get("text", "")))
        elif item.get("type") == "thinking":
            reasoning.append(str(item.get("thinking", "")))
        elif item.get("type") == "toolCall":
            arguments = item.get("arguments")
            calls.append(
                {
                    "tool_call_id": str(item.get("id", "")),
                    "function_name": str(item.get("name", "unknown")),
                    "arguments": arguments if isinstance(arguments, dict) else {},
                }
            )
    return (
        "\n".join(filter(None, text)),
        "\n".join(filter(None, reasoning)) or None,
        calls,
    )


def _usage_metrics(message):
    usage = message.get("usage")
    if not isinstance(usage, dict):
        return None
    cache = int(_number(usage.get("cacheRead")))
    cost = usage.get("cost") if isinstance(usage.get("cost"), dict) else {}
    return {
        "prompt_tokens": int(_number(usage.get("input"))) + cache,
        "completion_tokens": int(_number(usage.get("output"))),
        "cached_tokens": cache,
        "cost_usd": float(_number(cost.get("total"))),
    }


def _load_events(lines: Iterable[str]) -> list[dict[str, Any]]:
    events = []
    for line in lines:
        try:
            event = json.loads(line)
        except (json.JSONDecodeError, TypeError):
            continue
        if isinstance(event, dict):
            events.append(event)
    return events


def _messages(events):
    for index in range(len(events) - 1, -1, -1):
        event = events[index]
        if event.get("type") == "agent_end" and isinstance(event.get("messages"), list):
            return [
                message for message in event["messages"] if isinstance(message, dict)
            ] + [
                following["message"]
                for following in events[index + 1 :]
                if following.get("type") == "message_end"
                and isinstance(following.get("message"), dict)
            ]
    return [
        event["message"]
        for event in events
        if event.get("type") == "message_end" and isinstance(event.get("message"), dict)
    ]


def build_atif_trajectory(
    lines: Iterable[str],
    *,
    instruction: str,
    model_name: str | None,
    agent_version: str,
    agent_name: str = "open-harness",
) -> dict[str, Any]:
    events = _load_events(lines)
    messages = _messages(events)
    session_id = next(
        (
            str(event.get("sessionId") or event.get("id"))
            for event in events
            if event.get("type") == "session"
            and (event.get("sessionId") or event.get("id"))
        ),
        None,
    )
    steps, tool_steps = [], {}
    totals = {"prompt": 0, "completion": 0, "cached": 0, "cost": 0.0}
    has_instruction = any(
        message.get("role") == "user"
        and _content_text(message.get("content")).strip() == instruction.strip()
        for message in messages
    )
    if instruction and not has_instruction:
        steps.append({"step_id": 1, "source": "user", "message": instruction})
    for message in messages:
        role = message.get("role")
        if role == "user":
            steps.append(
                {
                    "step_id": len(steps) + 1,
                    "timestamp": _timestamp(message.get("timestamp")),
                    "source": "user",
                    "message": _content_text(message.get("content")),
                }
            )
        elif role == "assistant":
            text, reasoning, calls = _assistant_parts(message)
            metrics = _usage_metrics(message)
            step = {
                "step_id": len(steps) + 1,
                "timestamp": _timestamp(message.get("timestamp")),
                "source": "agent",
                "model_name": str(message.get("model") or model_name or "unknown"),
                "message": text,
                "llm_call_count": 1,
            }
            if reasoning:
                step["reasoning_content"] = reasoning
            if calls:
                step["tool_calls"] = calls
                for call in calls:
                    tool_steps[call["tool_call_id"]] = step
            if metrics:
                step["metrics"] = metrics
                totals["prompt"] += metrics["prompt_tokens"]
                totals["completion"] += metrics["completion_tokens"]
                totals["cached"] += metrics["cached_tokens"]
                totals["cost"] += metrics["cost_usd"]
            steps.append(step)
        elif role == "toolResult":
            call_id = str(message.get("toolCallId", ""))
            step = tool_steps.get(call_id)
            if step:
                step.setdefault("observation", {"results": []})["results"].append(
                    {
                        "source_call_id": call_id,
                        "content": _content_text(message.get("content")),
                        "extra": {
                            "is_error": bool(message.get("isError")),
                            "tool_name": str(message.get("toolName", "unknown")),
                        },
                    }
                )
    if not steps:
        steps.append(
            {"step_id": 1, "source": "user", "message": instruction or "Task started."}
        )
    for step in steps:
        if step.get("timestamp") is None:
            step.pop("timestamp", None)
    return {
        "schema_version": "ATIF-v1.7",
        **({"session_id": session_id} if session_id else {}),
        "agent": {
            "name": agent_name,
            "version": agent_version,
            **({"model_name": model_name} if model_name else {}),
        },
        "steps": steps,
        "final_metrics": {
            "total_prompt_tokens": totals["prompt"],
            "total_completion_tokens": totals["completion"],
            "total_cached_tokens": totals["cached"],
            "total_cost_usd": round(totals["cost"], 10),
            "total_steps": len(steps),
        },
        "extra": {"source_format": agent_name + "-jsonl"},
    }


def write_atif_trajectory(
    source: Path,
    target: Path,
    *,
    instruction: str,
    model_name: str | None,
    agent_version: str,
    agent_name: str = "open-harness",
):
    trajectory = build_atif_trajectory(
        source.read_text(encoding="utf-8", errors="replace").splitlines(),
        instruction=instruction,
        model_name=model_name,
        agent_version=agent_version,
        agent_name=agent_name,
    )
    target.write_text(
        json.dumps(trajectory, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return trajectory
