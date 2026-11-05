"""WorkspaceBench runner for the pinned OpenHarness CLI wheel.

This file is copied into Workspace-Bench's ``evaluation/src/agents`` directory
by Harbor-RSI's WorkspaceBench preparation step. It keeps the same OpenHarness
model configuration used by the prior local WorkspaceBench run: native
DeepSeek provider, high reasoning, images enabled, and the basic
read/bash/edit/write tools.
"""

from __future__ import annotations

from datetime import datetime, timezone
import json
import os
import re
import subprocess
import time
from typing import Any, Dict, Iterable, List, Optional


Json = Any
DEFAULT_TOOLS = ["read", "bash", "edit", "write"]


def _ensure_dir(path: str) -> None:
    os.makedirs(path, exist_ok=True)


def _write_json(path: str, value: Json) -> None:
    _ensure_dir(os.path.dirname(os.path.abspath(path)))
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(value, handle, ensure_ascii=False, indent=2)


def _write_text(path: str, value: str) -> None:
    _ensure_dir(os.path.dirname(os.path.abspath(path)))
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(value)


def _expand_provider_value(value: Json) -> Optional[str]:
    if not isinstance(value, str):
        return None
    expanded = os.path.expandvars(value).strip()
    if not expanded or re.search(r"\$\{[^}]+\}", expanded):
        return None
    return expanded


def _first_config_value(*values: Json) -> Optional[str]:
    for value in values:
        expanded = _expand_provider_value(value)
        if expanded:
            return expanded
    return None


def _iso_from_ms(value: Json) -> Optional[str]:
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        return None
    try:
        return (
            datetime.fromtimestamp(value / 1000.0, tz=timezone.utc)
            .isoformat()
            .replace("+00:00", "Z")
        )
    except Exception:
        return None


def _content_text(content: Json) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: List[str] = []
        for item in content:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict):
                if item.get("type") == "text" and isinstance(item.get("text"), str):
                    parts.append(item["text"])
                elif item.get("type") == "image":
                    parts.append(f"[image: {item.get('mimeType') or 'unknown'}]")
        return "\n".join(part for part in parts if part)
    if isinstance(content, dict):
        text = content.get("text") or content.get("content")
        return (
            text
            if isinstance(text, str)
            else json.dumps(content, ensure_ascii=False, sort_keys=True)
        )
    return "" if content is None else str(content)


def _load_events(text: str) -> List[Dict[str, Json]]:
    events: List[Dict[str, Json]] = []
    for raw in str(text or "").split("\n"):
        line = raw.strip()
        if not line:
            continue
        try:
            event = json.loads(line)
        except Exception:
            continue
        if isinstance(event, dict):
            events.append(event)
    return events


def _messages(events: Iterable[Dict[str, Json]]) -> List[Dict[str, Json]]:
    event_list = list(events)
    for event in reversed(event_list):
        if event.get("type") == "agent_end" and isinstance(event.get("messages"), list):
            return [item for item in event["messages"] if isinstance(item, dict)]
    return [
        event["message"]
        for event in event_list
        if event.get("type") == "message_end" and isinstance(event.get("message"), dict)
    ]


def _usage_from_message(message: Dict[str, Json]) -> Dict[str, int]:
    usage = message.get("usage") if isinstance(message.get("usage"), dict) else {}
    input_tokens = int(usage.get("input") or 0)
    output_tokens = int(usage.get("output") or 0)
    cache_read = int(usage.get("cacheRead") or 0)
    cache_write = int(usage.get("cacheWrite") or 0)
    return {
        "prompt_tokens": input_tokens + cache_read,
        "completion_tokens": output_tokens,
        "total_tokens": input_tokens + cache_read + output_tokens,
        "cache_read": cache_read,
        "cache_write": cache_write,
    }


def _assistant_parts(message: Dict[str, Json]) -> tuple[str, List[Dict[str, Json]]]:
    text_parts: List[str] = []
    tool_calls: List[Dict[str, Json]] = []
    content = message.get("content")
    if isinstance(content, list):
        for item in content:
            if not isinstance(item, dict):
                continue
            if item.get("type") == "text" and isinstance(item.get("text"), str):
                text_parts.append(item["text"])
            elif item.get("type") == "toolCall":
                args = item.get("arguments")
                tool_calls.append(
                    {
                        "type": "tool",
                        "role": "assistant",
                        "tool": str(item.get("name") or "unknown"),
                        "callID": str(item.get("id") or ""),
                        "input": args if isinstance(args, dict) else {},
                        "status": "started",
                    }
                )
    else:
        text = _content_text(content)
        if text:
            text_parts.append(text)
    return "\n".join(text_parts), tool_calls


def _parse_openharness_jsonl(
    stdout_text: str, *, prompt: str, started_at: float, base_url: str, model: str
) -> Dict[str, Json]:
    events = _load_events(stdout_text)
    messages = _messages(events)
    execution: List[Dict[str, Json]] = [
        {
            "type": "text",
            "role": "user",
            "content": str(prompt or ""),
            "timestamp": datetime.fromtimestamp(started_at, tz=timezone.utc)
            .isoformat()
            .replace("+00:00", "Z"),
        }
    ]
    usage_total = {
        "prompt_tokens": 0,
        "completion_tokens": 0,
        "total_tokens": 0,
        "cache_read": 0,
        "cache_write": 0,
    }
    last_text = ""
    tool_by_id: Dict[str, Dict[str, Json]] = {}
    turns = 0

    for message in messages:
        role = message.get("role")
        if role == "user":
            continue
        if role == "assistant":
            text, calls = _assistant_parts(message)
            usage = _usage_from_message(message)
            for key in usage_total:
                usage_total[key] += int(usage.get(key) or 0)
            if text:
                turns += 1
                last_text = text
                execution.append(
                    {
                        "type": "text",
                        "role": "assistant",
                        "content": text,
                        "timestamp": _iso_from_ms(message.get("timestamp")),
                        "llm": {
                            "provider": "deepseek",
                            "baseUrl": base_url,
                            "model": model,
                            "usage": usage,
                            "stopReason": message.get("stopReason"),
                            "errorMessage": message.get("error"),
                        },
                    }
                )
            for call in calls:
                call["timestamp"] = _iso_from_ms(message.get("timestamp"))
                tool_by_id[str(call.get("callID") or "")] = call
                execution.append(call)
        elif role == "toolResult":
            call_id = str(message.get("toolCallId") or "")
            item = tool_by_id.get(call_id)
            if item is None:
                item = {
                    "type": "tool",
                    "role": "tool",
                    "tool": str(message.get("toolName") or "unknown"),
                    "callID": call_id,
                    "input": {},
                }
                execution.append(item)
            item["output"] = _content_text(message.get("content"))
            item["status"] = "failed" if message.get("isError") else "completed"

    if not last_text:
        for event in reversed(events):
            if isinstance(event.get("text"), str):
                last_text = str(event["text"])
                break

    return {
        "lastText": last_text,
        "executionTrace": [
            item
            for item in execution
            if item.get("timestamp") is not None
            or item.get("type") != "text"
            or item.get("role") == "user"
        ],
        "usageTotal": usage_total,
        "turns": turns,
        "eventCount": len(events),
    }


def _venv_bin(venv: str, name: str) -> str:
    return os.path.join(venv, "bin", name)


def _venv_ready(venv_dir: str) -> bool:
    binary = _venv_bin(venv_dir, "open-harness")
    if not os.path.isfile(binary):
        return False
    proc = subprocess.run(
        [binary, "--version"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
    )
    return proc.returncode == 0


def _shared_venv_dir(sandbox_dir: str) -> str:
    configured = os.environ.get("OPEN_HARNESS_SHARED_VENV")
    if configured:
        return os.path.abspath(os.path.expandvars(configured))
    return os.path.join(
        os.path.dirname(os.path.abspath(sandbox_dir)), "_openharness_shared_venv"
    )


def _install_openharness(
    *, wheel_path: str, venv_dir: str, raw_dir: str
) -> tuple[bool, str]:
    if not os.path.isfile(wheel_path):
        return False, f"OpenHarness wheel not found: {wheel_path}"
    lock_dir = f"{venv_dir}.lock"
    waited = 0.0
    while True:
        try:
            os.mkdir(lock_dir)
            break
        except FileExistsError:
            if waited >= 900:
                return (
                    False,
                    f"Timed out waiting for OpenHarness shared venv lock: {lock_dir}",
                )
            time.sleep(2.0)
            waited += 2.0
    proc: Optional[subprocess.CompletedProcess[str]] = None
    try:
        if _venv_ready(venv_dir):
            proc = subprocess.run(
                [_venv_bin(venv_dir, "open-harness"), "--version"],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
        else:
            cmd = [
                "bash",
                "-lc",
                (
                    f"python3 -m venv --clear {shlex_quote(venv_dir)} && "
                    f"{shlex_quote(_venv_bin(venv_dir, 'python'))} -m pip install "
                    f"--disable-pip-version-check --no-input {shlex_quote(wheel_path)} && "
                    f"{shlex_quote(_venv_bin(venv_dir, 'open-harness'))} --version"
                ),
            ]
            proc = subprocess.run(
                cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
            )
    finally:
        try:
            os.rmdir(lock_dir)
        except OSError:
            pass
    _write_text(
        os.path.join(raw_dir, "openharness_install_stdout.txt"), proc.stdout or ""
    )
    _write_text(
        os.path.join(raw_dir, "openharness_install_stderr.txt"), proc.stderr or ""
    )
    _write_json(
        os.path.join(raw_dir, "openharness_venv.json"),
        {"path": venv_dir, "shared": True},
    )
    return proc.returncode == 0, (proc.stderr or proc.stdout or "").strip()


def shlex_quote(value: str) -> str:
    return "'" + str(value).replace("'", "'\"'\"'") + "'"


def _build_config(
    *,
    model: str,
    base_url: str,
    supports_images: bool,
    context_window: int,
    max_tokens: int,
    thinking: str,
) -> Dict[str, Json]:
    return {
        "model": {
            "id": model,
            "name": model,
            "api": "openai-completions",
            "provider": "deepseek",
            "baseUrl": str(base_url).rstrip("/"),
            "reasoning": True,
            "input": ["text", "image"] if supports_images else ["text"],
            "thinkingLevelMap": {
                "minimal": "minimal",
                "low": "low",
                "medium": "medium",
                "high": "high",
                "xhigh": "xhigh",
                "max": "max",
            },
            "contextWindow": context_window,
            "maxTokens": max_tokens,
            "cost": {"input": 0, "output": 0, "cacheRead": 0, "cacheWrite": 0},
        },
        "thinkingLevel": thinking,
        "tools": list(DEFAULT_TOOLS),
        "persist": False,
        "requestOptions": {"maxTokens": max_tokens},
        "resources": {"autoDiscover": True},
    }


def run(
    *,
    prompt: str,
    work_dir: str,
    sandbox_dir: str,
    timeout_s: float,
    api_provider: Dict[str, Json],
    agent_id: Optional[str] = None,
) -> Dict[str, Json]:
    started_at = time.time()
    _ensure_dir(sandbox_dir)
    raw_dir = os.path.join(sandbox_dir, "raw")
    _ensure_dir(raw_dir)

    model_value = _first_config_value(
        api_provider.get("model") if isinstance(api_provider, dict) else None,
        os.environ.get("OPEN_HARNESS_MODEL"),
    )
    model = (model_value or "deepseek-flash").split("/", 1)[-1]
    base_url = (
        _first_config_value(
            api_provider.get("baseUrl") if isinstance(api_provider, dict) else None,
            api_provider.get("base_url") if isinstance(api_provider, dict) else None,
            os.environ.get("DEEPSEEK_BASE_URL"),
        )
        or "https://api.deepseek.com"
    )
    api_key = _first_config_value(
        api_provider.get("apiKey") if isinstance(api_provider, dict) else None,
        api_provider.get("api_key") if isinstance(api_provider, dict) else None,
        os.environ.get("DEEPSEEK_API_KEY"),
    )
    wheel_path = _first_config_value(os.environ.get("OPEN_HARNESS_WHEEL"))
    if not api_key:
        return {
            "status": "error",
            "paths": [],
            "errorMessage": "Missing DEEPSEEK_API_KEY/apiProvider.apiKey for OpenHarness",
        }
    if not wheel_path:
        return {
            "status": "error",
            "paths": [],
            "errorMessage": "Missing OPEN_HARNESS_WHEEL for OpenHarness",
        }

    venv_dir = _shared_venv_dir(sandbox_dir)
    ok, install_message = _install_openharness(
        wheel_path=wheel_path, venv_dir=venv_dir, raw_dir=raw_dir
    )
    if not ok:
        return {"status": "error", "paths": [], "errorMessage": install_message[:4000]}

    context_window = int(os.environ.get("OPEN_HARNESS_CONTEXT_WINDOW") or "200000")
    max_tokens = int(os.environ.get("OPEN_HARNESS_MAX_TOKENS") or "65536")
    thinking = str(os.environ.get("OPEN_HARNESS_REASONING") or "high")
    supports_images = str(
        os.environ.get("OPEN_HARNESS_SUPPORTS_IMAGES") or "true"
    ).lower() not in {"0", "false", "no"}
    config = _build_config(
        model=model,
        base_url=base_url,
        supports_images=supports_images,
        context_window=context_window,
        max_tokens=max_tokens,
        thinking=thinking,
    )
    config_path = os.path.join(raw_dir, "openharness_config.json")
    _write_json(config_path, config)

    stdout_path = os.path.join(raw_dir, "openharness_stdout.jsonl")
    stderr_path = os.path.join(raw_dir, "openharness_stderr.log")
    cmd = [
        _venv_bin(venv_dir, "open-harness"),
        "--print",
        "--mode",
        "json",
        "--no-session",
        "--literal",
        "--config",
        config_path,
        str(prompt or ""),
    ]
    _write_json(
        os.path.join(raw_dir, "openharness_invocation.json"),
        {
            "cmd": cmd,
            "cwd": os.path.abspath(work_dir),
            "agentId": agent_id,
            "model": model,
            "baseUrl": base_url,
            "settings": {
                "thinking": thinking,
                "contextWindow": context_window,
                "maxTokens": max_tokens,
                "supportsImages": supports_images,
                "tools": list(DEFAULT_TOOLS),
            },
        },
    )

    env = os.environ.copy()
    env["DEEPSEEK_API_KEY"] = api_key
    stdout_text = ""
    stderr_text = ""
    exit_code = 1
    try:
        proc = subprocess.Popen(
            cmd,
            cwd=os.path.abspath(work_dir),
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        try:
            stdout_text, stderr_text = proc.communicate(
                timeout=timeout_s if timeout_s > 0 else None
            )
            exit_code = int(proc.returncode or 0)
        except subprocess.TimeoutExpired:
            exit_code = 124
            proc.terminate()
            try:
                stdout_text, stderr_text = proc.communicate(timeout=10)
            except subprocess.TimeoutExpired:
                proc.kill()
                stdout_text, stderr_text = proc.communicate()
    except Exception as error:
        stderr_text = f"{type(error).__name__}: {error}"
        exit_code = 1

    _write_text(stdout_path, stdout_text or "")
    _write_text(stderr_path, stderr_text or "")
    _write_text(os.path.join(raw_dir, "stdout.txt"), stdout_text or "")
    _write_text(os.path.join(raw_dir, "stderr.txt"), stderr_text or "")

    trace = _parse_openharness_jsonl(
        stdout_text or "",
        prompt=str(prompt or ""),
        started_at=started_at,
        base_url=base_url,
        model=model,
    )
    status = "ok"
    error_message = None
    if exit_code == 124:
        status = "timeout"
        error_message = f"Timeout after {timeout_s}s"
    elif exit_code != 0:
        status = "error"
        error_message = (stderr_text or stdout_text or "OpenHarness runner failed")[
            :4000
        ]

    return {
        "status": status,
        "paths": [],
        "errorMessage": error_message,
        "trace": {
            "runner": "openharness",
            "agentId": agent_id,
            "rawDir": raw_dir,
            "lastText": str(trace.get("lastText") or ""),
            "executionTrace": trace.get("executionTrace")
            if isinstance(trace.get("executionTrace"), list)
            else [],
            "llm": {"provider": "deepseek", "baseUrl": base_url, "model": model},
            "usageTotal": trace.get("usageTotal")
            if isinstance(trace.get("usageTotal"), dict)
            else {},
            "eventCount": trace.get("eventCount"),
            "stdoutPath": stdout_path,
            "stderrPath": stderr_path,
        },
        "metrics": {
            "turns": trace.get("turns")
            if isinstance(trace.get("turns"), int)
            else None,
            "promptTokens": int(
                (trace.get("usageTotal") or {}).get("prompt_tokens") or 0
            ),
            "completionTokens": int(
                (trace.get("usageTotal") or {}).get("completion_tokens") or 0
            ),
            "totalTokens": int(
                (trace.get("usageTotal") or {}).get("total_tokens") or 0
            ),
        },
        "durationMs": int((time.time() - started_at) * 1000),
    }
