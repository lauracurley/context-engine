"""Compact retrieval payloads with an explicit whole-payload byte ceiling."""

import json


def encode(value):
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def size(value):
    return len(encode(value).encode("utf-8"))


def pack(engine, items, token_budget=2000, state="ready", generation=None, gaps=(), **metadata):
    if type(token_budget) is not int or not 1024 <= token_budget <= 32000:
        raise ValueError("token_budget must be 1024..32000 for compact retrieval")
    result = {
        "environment": engine.config["environment"],
        "workspace": engine.config["workspace"],
        "state": state,
        "generation": generation,
        **metadata,
        "items": [],
        "gaps": [str(g)[:180] for g in gaps][:3],
        "content_is_untrusted": True,
        "budget": {
            "limit": token_budget,
            "used_bytes": 0,
            "omitted_items": len(items),
            "method": "compact JSON UTF-8 bytes; entire payload, excluding MCP envelope",
        },
    }

    def measure():
        # The byte count includes its own decimal representation.
        for _ in range(5):
            measured = size(result)
            if measured == result["budget"]["used_bytes"]:
                return measured
            result["budget"]["used_bytes"] = measured
        return size(result)

    if measure() > token_budget:
        raise ValueError("token_budget is too small for response metadata; increase it")
    for item in items:
        result["items"].append(item)
        result["budget"]["omitted_items"] -= 1
        if measure() > token_budget:
            result["items"].pop()
            result["budget"]["omitted_items"] += 1
    measure()
    return result
