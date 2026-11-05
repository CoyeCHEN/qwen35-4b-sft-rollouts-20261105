# ruff: noqa: SIM115 -- stream metadata handle is closed by the streaming generator finalizer
"""A single TMax Content route at an existing OpenAI-compatible HTTP boundary.

The installed Harness CLI and its transport remain unchanged. This process lives
with vLLM, imports its pinned XML parser, and exits with the inference lease.
"""

import gzip
import hashlib
import json
import os
import time
from pathlib import Path

import httpx
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse, StreamingResponse
from inline_stream import InlineXMLStream
from payload import content_payload
from transformers import AutoTokenizer


def create_app(mode, seed, tokenizer, upstream, key, audit, *, backend=None):
    if mode not in ("T0", "T1", "T2"):
        raise ValueError("Invalid frozen thinking mode")
    app = FastAPI()
    audit = Path(audit)
    audit.mkdir(parents=True, exist_ok=True)

    def authorize(request):
        if request.headers.get("authorization") != "Bearer " + key:
            raise HTTPException(401, "Unauthorized")

    @app.get("/healthz")
    async def health():
        return {"route": "inline_content", "mode": mode, "seed": seed}

    @app.get("/v1/models")
    async def models(request: Request):
        authorize(request)
        async with httpx.AsyncClient(transport=backend, timeout=10) as client:
            r = await client.get(
                upstream + "/models", headers={"Authorization": "Bearer " + key}
            )
            return JSONResponse(r.json(), status_code=r.status_code)

    @app.post("/v1/chat/completions")
    async def completion(request: Request):
        authorize(request)
        incoming = await request.json()
        if not incoming.get("stream"):
            raise HTTPException(400, "This candidate requires Streaming")
        # The native transport emits this DeepSeek-specific option; thinking
        # in this one TMax route is instead controlled by the template above.
        try:
            payload = content_payload(incoming, mode, seed)
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc
        ident = hashlib.sha256(os.urandom(32)).hexdigest()[:24]
        request_text = json.dumps(
            {
                "unix": time.time(),
                "incoming": incoming,
                "vllm_payload": payload,
                "mode": mode,
                "seed": seed,
            },
            ensure_ascii=False,
        )
        with gzip.open(audit / (ident + "-request.json.gz"), "wt") as f:
            f.write(request_text.replace(key, "<REDACTED_SERVICE_KEY>"))
        client = httpx.AsyncClient(transport=backend, timeout=600)
        try:
            response = await client.send(
                client.build_request(
                    "POST",
                    upstream + "/chat/completions",
                    json=payload,
                    headers={"Authorization": "Bearer " + key},
                ),
                stream=True,
            )
        except BaseException:
            await client.aclose()
            raise
        if response.is_error:
            body = await response.aread()
            status = response.status_code
            await response.aclose()
            await client.aclose()
            return JSONResponse(
                {
                    "error": {
                        "message": body.decode("utf-8", "replace"),
                        "type": "upstream_error",
                    }
                },
                status_code=status,
            )
        raw_text = []
        generated_ids = []
        metadata_file = gzip.open(audit / (ident + "-sse-metadata.jsonl.gz"), "wt")

        def record(frame):
            # Whole generated text is saved after joining chunks, so a secret
            # split across chunks can be removed. Headers are never recorded.
            metadata = {
                "unix": time.time(),
                "id": frame.get("id"),
                "usage": frame.get("usage"),
                "choices": [],
            }
            for c in frame.get("choices", []):
                text = (c.get("delta") or {}).get("content") or ""
                raw_text.append(text)
                generated_ids.extend(c.get("token_ids") or [])
                metadata["choices"].append(
                    {
                        "index": c.get("index"),
                        "finish_reason": c.get("finish_reason"),
                        "content_characters": len(text),
                    }
                )
            metadata_file.write(json.dumps(metadata) + "\n")

        async def converted():
            stream = InlineXMLStream(response, payload, tokenizer, record)
            try:
                async for chunk in stream:
                    yield chunk
            except Exception as exc:
                with gzip.open(audit / (ident + "-error.json.gz"), "wt") as f:
                    f.write(
                        json.dumps({"type": type(exc).__name__, "message": str(exc)})
                    )
                # Abort the response on protocol errors. A partial tool delta
                # is never emitted by InlineXMLStream before complete parsing.
                raise
            finally:
                metadata_file.close()
                joined = "".join(raw_text)
                record_text = {
                    "raw_generation_sha256": hashlib.sha256(
                        joined.encode()
                    ).hexdigest(),
                    "text": joined.replace(key, "<REDACTED_SERVICE_KEY>"),
                    "token_ids": generated_ids if key not in joined else None,
                    "secret_redacted": key in joined,
                }
                with gzip.open(audit / (ident + "-generation.json.gz"), "wt") as f:
                    f.write(json.dumps(record_text, ensure_ascii=False))
                await stream.aclose()
                await client.aclose()

        return StreamingResponse(converted(), media_type="text/event-stream")

    return app


if __name__ == "__main__":
    import argparse

    import uvicorn

    p = argparse.ArgumentParser()
    p.add_argument("--mode", choices=["T0", "T1", "T2"], required=True)
    p.add_argument("--seed", type=int, required=True)
    p.add_argument("--tokenizer", required=True)
    p.add_argument("--upstream", default="http://127.0.0.1:18169/v1")
    p.add_argument("--port", type=int, default=18170)
    p.add_argument("--audit", required=True)
    args = p.parse_args()
    os.umask(0o077)
    tok = AutoTokenizer.from_pretrained(args.tokenizer, local_files_only=True)
    app = create_app(
        args.mode, args.seed, tok, args.upstream, os.environ["VLLM_API_KEY"], args.audit
    )
    uvicorn.run(app, host="127.0.0.1", port=args.port, log_level="warning")
