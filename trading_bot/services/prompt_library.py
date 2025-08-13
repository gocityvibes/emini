# trading_bot/services/prompt_library.py
from __future__ import annotations

from typing import Dict, Any, List
from datetime import datetime
import asyncio
import copy

from .database import db

class PromptProfileError(Exception):
    """Raised when prompt profile operations fail"""
    pass

def _ensure_db() -> None:
    """Ensure database connection is started (safe in sync or async contexts)."""
    if not hasattr(db, '_initialized') or not getattr(db, '_initialized'):
        try:
            # If we're already inside an event loop, schedule start
            loop = asyncio.get_running_loop()
            loop.create_task(db.start())
        except RuntimeError:
            # No running loop: start synchronously
            asyncio.run(db.start())
        db._initialized = True

def get_profile(profile_id: str) -> dict:
    """Get prompt profile from storage (MongoDB or in-memory)."""
    try:
        _ensure_db()
        if getattr(db, 'use_memory', False):
            return _get_profile_memory(profile_id)
        else:
            return _get_profile_mongo(profile_id)
    except Exception as e:
        print(f"Error getting profile {profile_id}: {e}")
        return _get_default_profile()

def save_profile(profile_id: str, profile: dict) -> None:
    """Save prompt profile to storage."""
    try:
        profile = copy.deepcopy(profile)
        profile["updated_at"] = datetime.utcnow().isoformat()
        _ensure_db()
        if getattr(db, 'use_memory', False):
            _save_profile_memory(profile_id, profile)
        else:
            _save_profile_mongo(profile_id, profile)
    except Exception as e:
        raise PromptProfileError(f"Failed to save profile {profile_id}: {e}")

def list_profiles() -> List[str]:
    """List all available profile IDs."""
    try:
        _ensure_db()
        if getattr(db, 'use_memory', False):
            return list(_memory_profiles.keys()) or ["default"]
        else:
            return _list_profiles_mongo()
    except Exception as e:
        print(f"Error listing profiles: {e}")
        return ["default"]

# Memory storage for development/testing
_memory_profiles: Dict[str, dict] = {}

def _get_profile_memory(profile_id: str) -> dict:
    """Get profile from memory storage."""
    if profile_id not in _memory_profiles:
        _memory_profiles[profile_id] = _get_default_profile()
    return copy.deepcopy(_memory_profiles[profile_id])

def _save_profile_memory(profile_id: str, profile: dict) -> None:
    """Save profile to memory storage."""
    _memory_profiles[profile_id] = copy.deepcopy(profile)

def _get_profile_mongo(profile_id: str) -> dict:
    """Get profile from MongoDB."""
    try:
        collection = db.client[db.database_name]["prompt_profiles"]
        doc = collection.find_one({"_id": profile_id})
        if doc:
            doc.pop("_id", None)
            return doc
        # Create and return default if not found
        default = _get_default_profile()
        save_profile(profile_id, default)
        return default
    except Exception as e:
        print(f"MongoDB error getting profile {profile_id}: {e}")
        return _get_default_profile()

def _save_profile_mongo(profile_id: str, profile: dict) -> None:
    """Save profile to MongoDB."""
    try:
        collection = db.client[db.database_name]["prompt_profiles"]
        doc = copy.deepcopy(profile)
        doc["_id"] = profile_id
        collection.replace_one({"_id": profile_id}, doc, upsert=True)
    except Exception as e:
        raise PromptProfileError(f"MongoDB save failed: {e}")

def _list_profiles_mongo() -> List[str]:
    """List profiles from MongoDB."""
    try:
        collection = db.client[db.database_name]["prompt_profiles"]
        return [doc["_id"] for doc in collection.find({}, {"_id": 1})]
    except Exception as e:
        print(f"MongoDB error listing profiles: {e}")
        return ["default"]

def _get_default_profile() -> dict:
    """Get the default prompt profile."""
    return {
        "system": """You are an expert MES (Micro E-mini S&P 500) scalping trader.

Your job is to analyze market snapshots and make precise entry decisions for 1-point scalps.

Key principles:
- MES moves in 0.25 point increments
- Target: +1.00 point profit
- Risk: -1.25 point stop loss  
- Only trade during high-probability setups
- Focus on momentum and clean price action
- Session analysis: AM (8:30-10:30) vs PM (13:00-15:00)

Respond with JSON containing your trading decision.""",

        "guardrails": [

            "Must respect allowed_directions constraint",

            "Entry price must be realistic given current market data",

            "Stop loss must provide -1.25 point risk for scalps",

            "Take profit must target +1.00 point reward for scalps",

            "Confidence must reflect genuine setup quality",

            "No trades during low-volume or erratic conditions"

        ],

        "few_shot": [

            {

                "snapshot_hash": "example_001",

                "features": {

                    "current_price": 5125.50,

                    "trend_direction": "up",

                    "momentum": "strong",

                    "volume": "high",

                    "session": "AM",

                    "range_3bars": 2.75,

                    "rsi": 65,

                    "above_sma20": True

                },

                "label": "long",

                "rationale": "Strong uptrend with high volume, clean breakout above resistance at 5125. AM session momentum favorable for scalp long."

            },

            {

                "snapshot_hash": "example_002",

                "features": {

                    "current_price": 5098.75,

                    "trend_direction": "down",

                    "momentum": "strong",

                    "volume": "normal",

                    "session": "PM",

                    "range_3bars": 3.25,

                    "rsi": 35,

                    "below_sma20": True

                },

                "label": "short",

                "rationale": "Clear downtrend with momentum, break below 5100 support level. RSI oversold but momentum still strong for scalp short."

            }

        ],

        "weights": {

            "long_bias": 0.0,

            "short_bias": 0.0,

            "risk": 1.0

        },

        "updated_at": datetime.utcnow().isoformat()

    }

