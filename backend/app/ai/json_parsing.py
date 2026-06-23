import json
import re

_FENCE_RE = re.compile(r"```(?:json)?\s*(.*?)\s*```", re.DOTALL)


def _try_json_loads(text: str):
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return None


def extract_json_value(raw: str, open_char: str, close_char: str):
    """Best-effort extraction of a JSON value from messy model output.

    Strips ```json fences if present, then falls back to slicing between the
    first open_char and last close_char (handles prose wrapped around JSON).
    """
    fence_match = _FENCE_RE.search(raw)
    text = fence_match.group(1) if fence_match else raw.strip()

    data = _try_json_loads(text)
    if data is None:
        start, end = text.find(open_char), text.rfind(close_char)
        if start != -1 and end != -1 and end > start:
            data = _try_json_loads(text[start : end + 1])
    return data
