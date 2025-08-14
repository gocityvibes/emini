# trading_bot/json_guard.py
"""Global JSON guard: makes all json.dumps datetime-safe without rewriting your code.
Import this ONCE at startup (right after datetime_fix) to harden every json.dumps call.
"""
from __future__ import annotations

import json
from datetime import datetime
from typing import Any

# Keep a handle to the original dumps so we don't loop
_original_dumps = json.dumps

def _obj_to_serializable(obj: Any) -> Any:
    if isinstance(obj, datetime):
        return obj.isoformat()
    # Pydantic v2
    if hasattr(obj, "model_dump") and callable(getattr(obj, "model_dump")):
        return clean_for_ai(obj.model_dump())
    # Pydantic v1
    if hasattr(obj, "dict") and callable(getattr(obj, "dict")):
        return clean_for_ai(obj.dict())
    # Generic objects
    if hasattr(obj, "__dict__") and not isinstance(obj, (str, int, float, bool, bytes)):
        try:
            return clean_for_ai(vars(obj))
        except Exception:
            return str(obj)
    return obj

def clean_for_ai(data: Any) -> Any:
    if isinstance(data, dict):
        return {k: clean_for_ai(v) for k, v in data.items()}
    if isinstance(data, (list, tuple, set)):
        t = type(data)
        return t(clean_for_ai(v) for v in data)
    return _obj_to_serializable(data)

class DateTimeEncoder(json.JSONEncoder):
    def default(self, obj):
        ser = _obj_to_serializable(obj)
        if ser is not obj:
            return ser
        return super().default(obj)

def _safe_dumps(obj, *args, **kwargs):
    # If the caller already provided a custom encoder or default, don't interfere
    if "cls" in kwargs or "default" in kwargs:
        try:
            return _original_dumps(obj, *args, **kwargs)
        except TypeError:
            # Fall back to cleaning if their encoder still fails on datetime
            cleaned = clean_for_ai(obj)
            return _original_dumps(cleaned, *args, **kwargs)
    # Otherwise, clean & encode with our encoder
    cleaned = clean_for_ai(obj)
    return _original_dumps(cleaned, *args, cls=DateTimeEncoder, **kwargs)

# Monkey-patch globally
json.dumps = _safe_dumps  # type: ignore

print("✅ json_guard: global json.dumps patched for datetime safety")
