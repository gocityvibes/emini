# trading_bot/config.py - Complete Configuration with GPT-5 Integration
from __future__ import annotations

import os
from datetime import time
from typing import Any, Dict, List, Optional, Tuple

# -------------------------------------------------------------------
# Helpers (safe env parsing + small validators)
# -------------------------------------------------------------------
def _get_bool(key: str, default: bool) -> bool:
    raw = os.getenv(key)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "t", "yes", "y", "on"}

def _get_int(key: str, default: int) -> int:
    raw = os.getenv(key)
    if raw is None:
        return default
    try:
        return int(raw.strip())
    except (TypeError, ValueError):
        return default

def _get_float(key: str, default: float) -> float:
    raw = os.getenv(key)
    if raw is None:
        return default
    try:
        return float(raw.strip())
    except (TypeError, ValueError):
        return default

def _get_list(key: str, default: List[str]) -> List[str]:
    raw = os.getenv(key)
    if not raw:
        return default
    return [x.strip() for x in raw.split(",") if x.strip()]

def _parse_hhmm(s: str, fallback: time) -> time:
    try:
        hh, mm = s.strip().split(":")
        h, m = int(hh), int(mm)
        if 0 <= h <= 23 and 0 <= m <= 59:
            return time(h, m)
        return fallback
    except Exception:
        return fallback

def _clamp(v: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, v))

# -------------------------------------------------------------------
# Environment / Debug
# -------------------------------------------------------------------
ENVIRONMENT: str = os.getenv("ENVIRONMENT", "development")
DEBUG: bool = ENVIRONMENT == "development"

# -------------------------------------------------------------------
# Database Configuration
# -------------------------------------------------------------------
MONGODB_URL: str = os.getenv("MONGODB_URL", "mongodb://localhost:27017")
DATABASE_NAME: str = os.getenv("DATABASE_NAME", "trading_bot")

# -------------------------------------------------------------------
# OpenAI Configuration (GPT-5 + Hybrid Mode)
# -------------------------------------------------------------------
OPENAI_API_KEY: str = os.getenv("OPENAI_API_KEY", "")
USE_FULL_GPT5: bool = True  # constant flag for code clarity
MODEL_NAME: str = os.getenv("MODEL_NAME", "gpt-5")
DECISION_MODEL: str = os.getenv("DECISION_MODEL", "gpt-5")
OPENAI_CONCURRENCY: int = _get_int("OPENAI_CONCURRENCY", 8)
OPENAI_MAX_TOKENS: int = _get_int("OPENAI_MAX_TOKENS", 256)  # small cap

# Learning System Configuration
PROMPT_UPDATE_INTERVAL: int = _get_int("PROMPT_UPDATE_INTERVAL", 25)

# Hybrid Mode Configuration (optional GPT-4.1 prefiltering)
HYBRID_ENABLED: bool = _get_bool("HYBRID_ENABLED", True)
FT_MODEL_NAME_41: str = os.getenv("FT_MODEL_NAME_41", "ft:gpt-4.1-mini:org:model:xxxx")
HYBRID_SCORE_THRESHOLD: float = _get_float("HYBRID_SCORE_THRESHOLD", 80.0)
HYBRID_LOG_NON_PASSES: bool = _get_bool("HYBRID_LOG_NON_PASSES", True)

# -------------------------------------------------------------------
# Trading Configuration - MES Scalping Strategy
# -------------------------------------------------------------------
SCALP_ONLY: bool = _get_bool("SCALP_ONLY", True)
SCALP_TP_POINTS: float = _get_float("SCALP_TP_POINTS", 1.0)   # +1.00
SCALP_SL_POINTS: float = _get_float("SCALP_SL_POINTS", 1.25)  # -1.25
ALLOW_LONG: bool = _get_bool("ALLOW_LONG", True)
ALLOW_SHORT: bool = _get_bool("ALLOW_SHORT", True)
CONFIDENCE_THRESHOLD: float = _clamp(_get_float("CONFIDENCE_THRESHOLD", 0.85), 0.0, 1.0)
COOLDOWN_SECONDS: int = _get_int("COOLDOWN_SECONDS", 120)
MAX_TRADES_PER_SESSION: int = _get_int("MAX_TRADES_PER_SESSION", 3)

# -------------------------------------------------------------------
# Market Movement Guardrails
# -------------------------------------------------------------------
SOFT_MOVEMENT_ENABLED: bool = _get_bool("SOFT_MOVEMENT_ENABLED", True)
MIN_SCALP_RANGE_POINTS: float = _get_float("MIN_SCALP_RANGE_POINTS", 1.0)  # last 3 bars total range

# -------------------------------------------------------------------
# Trading Sessions (HH:MM 24h, typically US/Eastern; actual tz handled upstream)
# -------------------------------------------------------------------
SESSION_AM_START: time = _parse_hhmm(os.getenv("SESSION_AM_START", "08:30"), time(8, 30))
SESSION_AM_END: time = _parse_hhmm(os.getenv("SESSION_AM_END", "10:30"), time(10, 30))
SESSION_PM_START: time = _parse_hhmm(os.getenv("SESSION_PM_START", "13:00"), time(13, 0))
SESSION_PM_END: time = _parse_hhmm(os.getenv("SESSION_PM_END", "15:00"), time(15, 0))

# -------------------------------------------------------------------
# Training and Simulation
# -------------------------------------------------------------------
DAILY_TRAINING_TRADES: int = _get_int("DAILY_TRAINING_TRADES", 450)
SIMULATION_SCENARIOS: List[str] = _get_list("SIMULATION_SCENARIOS", ["trend", "chop", "mixed"])
DAILY_SIMULATION_COUNT: int = _get_int("DAILY_SIMULATION_COUNT", 100)
SYMBOLS: List[str] = _get_list("SYMBOLS", ["MES"])

# -------------------------------------------------------------------
# Legacy Configuration (maintained for compatibility)
# -------------------------------------------------------------------
TREND_SCENARIO_RATIO: float = _get_float("TREND_SCENARIO_RATIO", 0.33)
CHOP_SCENARIO_RATIO: float = _get_float("CHOP_SCENARIO_RATIO", 0.33)
MIXED_SCENARIO_RATIO: float = _get_float("MIXED_SCENARIO_RATIO", 0.34)
RISK_PER_TRADE: float = _get_float("RISK_PER_TRADE", 0.02)

# -------------------------------------------------------------------
# WebSocket Configuration
# -------------------------------------------------------------------
WEBSOCKET_UPDATE_INTERVAL: int = _get_int("WEBSOCKET_UPDATE_INTERVAL", 2)  # seconds

# -------------------------------------------------------------------
# API Configuration
# -------------------------------------------------------------------
API_HOST: str = os.getenv("API_HOST", "0.0.0.0")
# Prefer API_PORT if provided; fall back to PORT (Render/Heroku-style)
API_PORT: int = _get_int("API_PORT", _get_int("PORT", 8000))
CORS_ORIGINS: List[str] = _get_list(
    "CORS_ORIGINS",
    [
        "http://localhost:3000",     # Local development
        "https://*.netlify.app",     # Netlify deployments
        "*"
    ],
)

# -------------------------------------------------------------------
# Market Data Configuration (used by simulators/generators)
# -------------------------------------------------------------------
TIMEFRAMES: List[str] = _get_list("TIMEFRAMES", ["1m", "5m", "15m", "1h"])
CANDLES_PER_SIMULATION: int = _get_int("CANDLES_PER_SIMULATION", 100)
BASE_PRICE_RANGE: Tuple[float, float] = (
    _get_float("BASE_PRICE_MIN", 4800.0),
    _get_float("BASE_PRICE_MAX", 5200.0),
)
VOLATILITY_RANGES: Dict[str, Tuple[float, float]] = {
    "low": (
        _get_float("VOL_LOW_MIN", 0.005),
        _get_float("VOL_LOW_MAX", 0.015),
    ),
    "medium": (
        _get_float("VOL_MED_MIN", 0.015),
        _get_float("VOL_MED_MAX", 0.030),
    ),
    "high": (
        _get_float("VOL_HIGH_MIN", 0.030),
        _get_float("VOL_HIGH_MAX", 0.060),
    ),
}

# -------------------------------------------------------------------
# Scenario Presets (one-click)
# -------------------------------------------------------------------
SCENARIO_PRESETS: Dict[str, Dict[str, Any]] = {
    "trend_am": {
        "confidence_threshold": 0.85,
        "soft_movement_enabled": True,
        "min_scalp_range_points": 1.0,
        "cooldown_seconds": 120,
        "max_trades_per_session": 3,
    },
    "chop_pm": {
        "confidence_threshold": 0.88,
        "soft_movement_enabled": True,
        "min_scalp_range_points": 1.2,
        "cooldown_seconds": 120,
        "max_trades_per_session": 3,
    },
    "news_spike": {
        "confidence_threshold": 0.90,
        "soft_movement_enabled": False,
        "min_scalp_range_points": 0.5,
        "cooldown_seconds": 180,
        "max_trades_per_session": 2,
    },
}

# -------------------------------------------------------------------
# Scenario Scheduling (optional auto time-of-day preset switching)
# -------------------------------------------------------------------
SCENARIO_SCHEDULE: Dict[str, Any] = {
    "enabled": _get_bool("SCENARIO_SCHEDULE_ENABLED", False),
    "windows": [
        {
            "start": os.getenv("SCEN_WIN1_START", "08:30"),
            "end": os.getenv("SCEN_WIN1_END", "10:30"),
            "preset": os.getenv("SCEN_WIN1_PRESET", "trend_am"),
        },
        {
            "start": os.getenv("SCEN_WIN2_START", "13:00"),
            "end": os.getenv("SCEN_WIN2_END", "15:00"),
            "preset": os.getenv("SCEN_WIN2_PRESET", "chop_pm"),
        },
    ],
}

# Validate schedule windows
_valid_windows: List[Dict[str, str]] = []
for w in SCENARIO_SCHEDULE.get("windows", []):
    try:
        start_s = str(w.get("start", "")).strip()
        end_s = str(w.get("end", "")).strip()
        preset = str(w.get("preset", "")).strip()
        if not start_s or not end_s or preset not in SCENARIO_PRESETS:
            continue
        _ = _parse_hhmm(start_s, None)  # type: ignore
        _ = _parse_hhmm(end_s, None)    # type: ignore
        _valid_windows.append({"start": start_s, "end": end_s, "preset": preset})
    except Exception:
        continue
if _valid_windows or not SCENARIO_SCHEDULE.get("windows"):
    SCENARIO_SCHEDULE["windows"] = _valid_windows

# -------------------------------------------------------------------
# Configuration Sanity Check Summary
# -------------------------------------------------------------------
CONFIG_SANITY: Dict[str, Any] = {
    "environment": ENVIRONMENT,
    "strategy": "MES_SCALP_ONLY" if SCALP_ONLY else "GENERIC",
    "model": MODEL_NAME,
    "scalp_tp": SCALP_TP_POINTS,
    "scalp_sl": SCALP_SL_POINTS,
    "confidence_min": CONFIDENCE_THRESHOLD,
    "max_trades_per_session": MAX_TRADES_PER_SESSION,
    "cooldown_seconds": COOLDOWN_SECONDS,
    "soft_movement": SOFT_MOVEMENT_ENABLED,
    "min_range_points": MIN_SCALP_RANGE_POINTS,
    "sessions": {
        "am": f"{SESSION_AM_START.strftime('%H:%M')}-{SESSION_AM_END.strftime('%H:%M')}",
        "pm": f"{SESSION_PM_START.strftime('%H:%M')}-{SESSION_PM_END.strftime('%H:%M')}",
    },
    "scenario_schedule_enabled": SCENARIO_SCHEDULE.get("enabled", False),
    "active_presets": (
        [w["preset"] for w in SCENARIO_SCHEDULE.get("windows", [])]
        if SCENARIO_SCHEDULE.get("enabled", False)
        else ["default"]
    ),
    "daily_training_target": DAILY_TRAINING_TRADES,
    "openai_concurrency": OPENAI_CONCURRENCY,
    "max_tokens": OPENAI_MAX_TOKENS,
    "symbols": SYMBOLS,
    "cors_origins_count": len(CORS_ORIGINS),
    "hybrid_mode": HYBRID_ENABLED,
    "prompt_update_interval": PROMPT_UPDATE_INTERVAL,
}
