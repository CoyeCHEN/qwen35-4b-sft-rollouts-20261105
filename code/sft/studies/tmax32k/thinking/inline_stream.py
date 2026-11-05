"""Content-only SSE adapter, retained verbatim from the passing candidate.
No structured reasoning route or route compatibility switch.
"""

import json

import httpx


class InlineXMLStream(httpx.AsyncByteStream):
    def __init__(self, response, request_payload, tokenizer, observer=None):
        self.response, self.request_payload, self.tokenizer = (
            response,
            request_payload,
            tokenizer,
        )
        self.observer = observer

    async def __aiter__(self):
        from boundary_safe_xml import extract_complete_xml
        from vllm.entrypoints.openai.chat_completion.protocol import (
            ChatCompletionRequest,
        )

        buf = b""
        raw = ""
        sent = 0
        finished = False
        enabled = self.request_payload.get("chat_template_kwargs", {}).get(
            "enable_thinking", False
        )

        def event(delta, finish=None):
            return (
                "data: "
                + json.dumps(
                    {
                        "choices": [
                            {"index": 0, "delta": delta, "finish_reason": finish}
                        ]
                    },
                    ensure_ascii=False,
                )
                + "\n\n"
            ).encode()

        async for block in self.response.aiter_bytes():
            buf += block
            while b"\n\n" in buf:
                frame, buf = buf.split(b"\n\n", 1)
                for line in frame.decode().splitlines():
                    if not line.startswith("data:"):
                        continue
                    data = line[5:].strip()
                    if data == "[DONE]":
                        if not finished:
                            raise ValueError("Raw XML stream missing finish_reason")
                        yield b"data: [DONE]\n\n"
                        continue
                    obj = json.loads(data)
                    if self.observer:
                        self.observer(obj)
                    if obj.get("error"):
                        yield frame + b"\n\n"
                        continue
                    if obj.get("usage"):
                        yield (
                            "data: "
                            + json.dumps({"choices": [], "usage": obj["usage"]})
                            + "\n\n"
                        ).encode()
                    for choice in obj.get("choices", []):
                        if choice.get("index", 0) != 0:
                            continue
                        delta = choice.get("delta") or {}
                        if (
                            delta.get("tool_calls")
                            or delta.get("reasoning")
                            or delta.get("reasoning_content")
                        ):
                            raise ValueError(
                                "Inline route received structured parser output; do not mix routes"
                            )
                        raw += delta.get("content") or ""
                        # An XML example inside reasoning is never an action.
                        # The open <think> is already part of the input prefix.
                        thought_open = enabled or raw.lstrip().startswith("<think>")
                        closed = raw.find("</think>") if thought_open else -1
                        action_start = (
                            closed + len("</think>")
                            if thought_open and closed >= 0
                            else (None if thought_open else 0)
                        )
                        at = (
                            raw.find("<tool_call>", action_start)
                            if action_start is not None
                            and self.request_payload.get("tools")
                            else -1
                        )
                        safe = (
                            at
                            if at >= 0
                            else max(sent, len(raw) - len("<tool_call>") + 1)
                        )
                        if safe > sent:
                            yield event({"content": raw[sent:safe]})
                            sent = safe
                        finish = choice.get("finish_reason")
                        if finish:
                            finished = True
                            if finish == "length":
                                # Never make truncated XML executable.
                                if at < 0 and len(raw) > sent:
                                    yield event({"content": raw[sent:]})
                                    sent = len(raw)
                                yield event({}, "length")
                                continue
                            if finish != "stop":
                                raise ValueError(
                                    "Unexpected raw-content finish reason " + finish
                                )
                            if thought_open and action_start is None:
                                raise ValueError(
                                    "Thinking did not close at normal stop"
                                )
                            if at < 0:
                                if len(raw) > sent:
                                    yield event({"content": raw[sent:]})
                                    sent = len(raw)
                                yield event({}, "stop")
                                continue
                            if not raw.rstrip().endswith("</tool_call>"):
                                raise ValueError("Unclosed tool XML at normal stop")
                            req = ChatCompletionRequest(
                                model=self.request_payload["model"],
                                messages=[],
                                tools=self.request_payload.get("tools"),
                            )
                            parsed = extract_complete_xml(
                                self.tokenizer, raw[action_start:], req
                            )
                            if not parsed.tools_called:
                                raise ValueError("Complete XML did not yield tools")
                            for tc in parsed.tool_calls:
                                try:
                                    json.loads(tc.function.arguments)
                                except (TypeError, json.JSONDecodeError) as e:
                                    raise ValueError(
                                        "Complete XML parser returned invalid argument JSON"
                                    ) from e
                            calls = [
                                {
                                    "index": i,
                                    "id": tc.id,
                                    "type": "function",
                                    "function": {
                                        "name": tc.function.name,
                                        "arguments": tc.function.arguments,
                                    },
                                }
                                for i, tc in enumerate(parsed.tool_calls)
                            ]
                            yield event({"tool_calls": calls})
                            yield event({}, "tool_calls")
        if buf:
            raise ValueError("Unterminated SSE frame")

    async def aclose(self):
        await self.response.aclose()
