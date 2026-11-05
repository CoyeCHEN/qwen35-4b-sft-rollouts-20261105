"""The one TMax template policy, shared by HTTP and fixed-state probes."""

import copy


def thinking_enabled(mode, messages):
    if mode not in ("T0", "T1", "T2"):
        raise ValueError("Invalid frozen thinking mode")
    return mode == "T2" or (
        mode == "T1"
        and bool(messages)
        and messages[-1]["role"] in ("tool", "toolResult")
    )


def content_payload(incoming, mode, seed):
    payload = copy.deepcopy(incoming)
    if any(
        m.get("reasoning") or m.get("reasoning_content") for m in payload["messages"]
    ):
        raise ValueError("Structured reasoning is outside this Content-only route")
    if payload.get("chat_template_kwargs"):
        raise ValueError("Thinking mode is owned by the frozen campaign")
    enabled = thinking_enabled(mode, payload["messages"])
    # Native compaction/branch summaries use no tools and explicitly request
    # reasoning off. Preserve that auxiliary policy in every Agent mode.
    if not payload.get("tools"):
        enabled = False
    if mode != "T0":
        payload["chat_template_kwargs"] = {"enable_thinking": enabled}
    payload.update(
        tool_choice="none", seed=seed, top_p=1.0, top_k=-1, return_token_ids=True
    )
    payload.pop("thinking", None)
    return payload
