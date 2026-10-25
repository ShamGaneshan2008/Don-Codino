"""Parse supported Codex JSONL metadata without interpreting it as trusted commands."""

import json


def parse(line: str) -> dict:
    try:
        event = json.loads(line)
    except (ValueError, TypeError):
        return {}
    if not isinstance(event, dict):
        return {}
    if event.get("type") == "thread.started" and isinstance(event.get("thread_id"), str):
        return {"session_id": event["thread_id"][:200]}
    if event.get("type") == "turn.completed" and isinstance(event.get("usage"), dict):
        return {
            "usage": {
                key: value
                for key, value in event["usage"].items()
                if key in {"input_tokens", "cached_input_tokens", "output_tokens"}
                and type(value) is int
                and value >= 0
            }
        }
    return {}
