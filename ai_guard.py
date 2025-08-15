# trading_bot/ai_guard.py
"""Wraps get_trade_decision to ensure ALL inputs are datetime-safe before
they ever reach OpenAI or any json.dumps inside ai_service.
Import this once at startup (after datetime_fix)."""

from typing import Any
from trading_bot.datetime_fix import clean_for_ai

# Import target module and grab original
from trading_bot.services import ai_service as _ai_service
_original_get_trade_decision = _ai_service.get_trade_decision

def _wrapped_get_trade_decision(*args: Any, **kwargs: Any):
    # Clean everything deeply (dicts, lists, datetimes, pydantic models)
    safe_args = clean_for_ai(list(args))
    safe_kwargs = clean_for_ai(dict(kwargs))
    return _original_get_trade_decision(*safe_args, **safe_kwargs)

# Monkey-patch
_ai_service.get_trade_decision = _wrapped_get_trade_decision

print("✅ ai_guard: get_trade_decision wrapped with datetime-safe cleaner")
