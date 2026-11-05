"""Black-box installed OpenHarness CLI/tool check, using only a loopback fixture.

Run with the installed agent's Python: python cli_contract_probe.py /path/open-harness.
No Harness internal module is imported; no task instructions or solutions are read.
"""

import json
import os
import subprocess
import sys
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, override


def probe(cli: str) -> dict[str, Any]:
    calls = []
    commands = [
        {
            "command": "printf 'readiness-stdout\\n'; printf 'readiness-stderr\\n' >&2; exit 7",
            "timeout": 10,
        },
        {"command": "printf 'readiness-timeout\\n'; sleep 2", "timeout": 0.05},
        {"command": "printf '%s' \"$HARBOR_READINESS_SENTINEL\"", "timeout": 10},
    ]

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            calls.append(
                json.loads(self.rfile.read(int(self.headers["content-length"])))
            )
            n = len(calls) - 1
            delta: dict[str, Any] = {"content": "readiness complete"}
            if n < len(commands):
                delta = {
                    "tool_calls": [
                        {
                            "index": 0,
                            "id": f"probe-{n}",
                            "type": "function",
                            "function": {
                                "name": "bash",
                                "arguments": json.dumps(commands[n]),
                            },
                        }
                    ]
                }
            delta["reasoning_content"] = "deterministic infrastructure fixture"
            chunks = [
                {
                    "id": "readiness",
                    "model": "fixture",
                    "choices": [{"index": 0, "delta": delta, "finish_reason": None}],
                },
                {
                    "choices": [
                        {
                            "index": 0,
                            "delta": {},
                            "finish_reason": "tool_calls"
                            if n < len(commands)
                            else "stop",
                        }
                    ],
                    "usage": {
                        "prompt_tokens": 10,
                        "completion_tokens": 5,
                        "total_tokens": 15,
                    },
                },
            ]
            body = (
                "".join("data: " + json.dumps(c) + "\n\n" for c in chunks)
                + "data: [DONE]\n\n"
            ).encode()
            self.send_response(200)
            self.send_header("content-type", "text/event-stream")
            self.send_header("content-length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        @override
        def log_message(self, format: str, *args: Any) -> None:
            pass

    with tempfile.TemporaryDirectory(prefix="harbor-cli-contract-") as temp:
        root = Path(temp)
        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        config = {
            "model": {
                "id": "fixture",
                "api": "openai-completions",
                "provider": "deepseek",
                "baseUrl": f"http://127.0.0.1:{server.server_port}",
                "reasoning": True,
                "input": ["text"],
                "contextWindow": 262144,
                "maxTokens": 65536,
                "cost": {"input": 0, "output": 0, "cacheRead": 0, "cacheWrite": 0},
            },
            "thinkingLevel": "off",
            "persist": True,
            "sessionDir": str(root / "sessions"),
            "tools": ["bash"],
            "resources": {
                "autoDiscover": False,
                "skillsEnabled": False,
                "templatesEnabled": False,
            },
            "enableAgentTool": False,
            "enableSkillTool": False,
            "toolSearch": "off",
            "finish": {"enabled": False},
            "backgroundJobs": {"enabled": False},
        }
        (root / "config.json").write_text(json.dumps(config))
        (root / "prompt.txt").write_text(
            "Deterministic infrastructure fixture; execute supplied tools only."
        )
        try:
            result = subprocess.run(
                [
                    cli,
                    "--cwd",
                    str(root),
                    "--print",
                    "--mode",
                    "json",
                    "--config",
                    str(root / "config.json"),
                    "--prompt-file",
                    str(root / "prompt.txt"),
                ],
                capture_output=True,
                text=True,
                timeout=45,
                env={
                    **os.environ,
                    "DEEPSEEK_API_KEY": "readiness-loopback-fixture",
                    "HARBOR_READINESS_SENTINEL": "child-env-ok",
                    "NO_PROXY": "127.0.0.1,localhost",
                    "no_proxy": "127.0.0.1,localhost",
                },
            )
        finally:
            server.shutdown()
            server.server_close()
        # The last request carries all previous tool observations.
        final_tools = (
            [m for m in calls[-1].get("messages", []) if m.get("role") == "tool"]
            if calls
            else []
        )
        text = json.dumps(final_tools)
        stdout_ok = "readiness-stdout" in text and "readiness-stderr" in text
        exit_ok = "code 7" in text or '"exitCode": 7' in text or 'exitCode\\":7' in text
        timeout_ok = "timed out" in text.lower() or '"timeout"' in text
        env_ok = "child-env-ok" in text
        report = {
            "cli_exit_code": result.returncode,
            "loopback_requests": len(calls),
            "observations": len(final_tools),
            "stdout_stderr": stdout_ok,
            "exit_code": exit_ok,
            "timeout": timeout_ok,
            "child_environment": env_ok,
            "external_model_called": False,
            "tool_messages": final_tools,
            "stderr": result.stderr[-2000:],
        }
        if (
            result.returncode
            or len(final_tools) != 3
            or not all((stdout_ok, exit_ok, timeout_ok, env_ok))
        ):
            raise RuntimeError(json.dumps(report))
        return report


if __name__ == "__main__":
    print(json.dumps(probe(sys.argv[1])))
