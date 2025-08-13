# trading_bot/services/outcome_logger.py
from __future__ import annotations

import uuid
from typing import Dict, Any
from datetime import datetime

from .database import db

def log_decision(doc: dict) -> str:
    """
    Log AI trading decision to MongoDB.
    Returns decision_id for linking with outcomes.
    """
    decision_id = str(uuid.uuid4())
    
    decision_doc = {
        "decision_id": decision_id,
        "ts": datetime.utcnow(),
        "symbol": doc.get("symbol", "MES"),
        "snapshot_id": doc.get("snapshot_id"),
        "snapshot_hash": doc.get("snapshot_hash"),
        "profile_id": doc.get("profile_id", "default"),
        "model": doc.get("model", "gpt-5"),
        
        # Decision data
        "direction": doc.get("direction"),
        "entry": doc.get("entry"),
        "sl": doc.get("sl"),
        "tp": doc.get("tp"),
        "confidence": doc.get("confidence"),
        "reasoning": doc.get("reasoning"),
        "contract_qty": doc.get("contract_qty", 1),
        "constraints": doc.get("constraints", {}),
        "policy_id": doc.get("policy_id"),
        
        # Metadata
        "session": doc.get("session"),
        "market_condition": doc.get("market_condition"),
        "scenario": doc.get("scenario")
    }
    
    try:
        if db.use_memory:
            _log_decision_memory(decision_doc)
        else:
            _log_decision_mongo(decision_doc)
    except Exception as e:
        print(f"Error logging decision {decision_id}: {e}")
    
    return decision_id

def log_outcome(doc: dict) -> None:
    """Log trade outcome to MongoDB"""
    outcome_doc = {
        "outcome_id": str(uuid.uuid4()),
        "decision_id": doc.get("decision_id"),
        "ts": datetime.utcnow(),
        
        # Trade results
        "exit": doc.get("exit"),
        "pnl_ticks": doc.get("pnl_ticks"),
        "pnl_usd": doc.get("pnl_usd"),
        "duration_s": doc.get("duration_s"),
        "result": doc.get("result"),  # "win"|"loss"|"be"
        "slipped_ticks": doc.get("slipped_ticks", 0),
        
        # Additional metrics
        "mae_ticks": doc.get("mae_ticks"),  # Maximum Adverse Excursion
        "mfe_ticks": doc.get("mfe_ticks"),  # Maximum Favorable Excursion
        "hit_target": doc.get("hit_target", False),  # True if TP hit, False if SL hit
        
        # Metadata
        "notes": doc.get("notes")
    }
    
    try:
        if db.use_memory:
            _log_outcome_memory(outcome_doc)
        else:
            _log_outcome_mongo(outcome_doc)
    except Exception as e:
        print(f"Error logging outcome for decision {doc.get('decision_id')}: {e}")

def log_prefilter(snapshot_meta: dict, score_doc: dict) -> None:
    """Log prefilter score (hybrid mode only)"""
    prefilter_doc = {
        "prefilter_id": str(uuid.uuid4()),
        "ts": datetime.utcnow(),
        "symbol": snapshot_meta.get("symbol", "MES"),
        "snapshot_id": snapshot_meta.get("snapshot_id"),
        "snapshot_hash": snapshot_meta.get("snapshot_hash"),
        "profile_id": snapshot_meta.get("profile_id", "default"),
        "model": score_doc.get("model", "ft:gpt-4.1"),
        
        # Prefilter results
        "score": score_doc.get("score"),
        "label": score_doc.get("label"),  # "pass"|"fail"
        "rationale": score_doc.get("rationale"),
        "policy_id": score_doc.get("policy_id"),
        "threshold_used": snapshot_meta.get("threshold_used"),
        
        # Context
        "session": snapshot_meta.get("session"),
        "market_condition": snapshot_meta.get("market_condition")
    }
    
    try:
        if db.use_memory:
            _log_prefilter_memory(prefilter_doc)
        else:
            _log_prefilter_mongo(prefilter_doc)
    except Exception as e:
        print(f"Error logging prefilter: {e}")

# Memory storage for development/testing
_memory_decisions = []
_memory_outcomes = []
_memory_prefilters = []

def _log_decision_memory(doc: dict) -> None:
    """Log decision to memory storage"""
    _memory_decisions.append(doc.copy())

def _log_outcome_memory(doc: dict) -> None:
    """Log outcome to memory storage"""
    _memory_outcomes.append(doc.copy())

def _log_prefilter_memory(doc: dict) -> None:
    """Log prefilter to memory storage"""
    _memory_prefilters.append(doc.copy())

def _log_decision_mongo(doc: dict) -> None:
    """Log decision to MongoDB"""
    try:
        collection = db.client[db.database_name]["decisions"]
        collection.insert_one(doc)
    except Exception as e:
        raise Exception(f"MongoDB decision logging failed: {e}")

def _log_outcome_mongo(doc: dict) -> None:
    """Log outcome to MongoDB"""
    try:
        collection = db.client[db.database_name]["outcomes"]
        collection.insert_one(doc)
    except Exception as e:
        raise Exception(f"MongoDB outcome logging failed: {e}")

def _log_prefilter_mongo(doc: dict) -> None:
    """Log prefilter to MongoDB"""
    try:
        collection = db.client[db.database_name]["prefilter"]
        collection.insert_one(doc)
    except Exception as e:
        raise Exception(f"MongoDB prefilter logging failed: {e}")

def get_recent_outcomes(profile_id: str, limit: int = 500) -> list:
    """Get recent outcomes for learning system"""
    try:
        if db.use_memory:
            # Filter by profile_id and get recent outcomes
            decisions_by_profile = [d for d in _memory_decisions if d.get("profile_id") == profile_id]
            decision_ids = [d["decision_id"] for d in decisions_by_profile]
            outcomes = [o for o in _memory_outcomes if o.get("decision_id") in decision_ids]
            return sorted(outcomes, key=lambda x: x.get("ts", datetime.min), reverse=True)[:limit]
        else:
            return _get_recent_outcomes_mongo(profile_id, limit)
    except Exception as e:
        print(f"Error getting recent outcomes: {e}")
        return []

def _get_recent_outcomes_mongo(profile_id: str, limit: int) -> list:
    """Get recent outcomes from MongoDB"""
    try:
        # First get recent decisions for this profile
        decisions_coll = db.client[db.database_name]["decisions"]
        recent_decisions = list(decisions_coll.find(
            {"profile_id": profile_id},
            {"decision_id": 1}
        ).sort("ts", -1).limit(limit))
        
        decision_ids = [d["decision_id"] for d in recent_decisions]
        
        # Then get outcomes for those decisions
        outcomes_coll = db.client[db.database_name]["outcomes"]
        outcomes = list(outcomes_coll.find(
            {"decision_id": {"$in": decision_ids}}
        ).sort("ts", -1))
        
        return outcomes
    except Exception as e:
        print(f"MongoDB error getting recent outcomes: {e}")
        return []

def get_decision_context(decision_id: str) -> dict:
    """Get the original decision context for an outcome"""
    try:
        if db.use_memory:
            for decision in _memory_decisions:
                if decision.get("decision_id") == decision_id:
                    return decision
            return {}
        else:
            return _get_decision_context_mongo(decision_id)
    except Exception as e:
        print(f"Error getting decision context: {e}")
        return {}

def _get_decision_context_mongo(decision_id: str) -> dict:
    """Get decision context from MongoDB"""
    try:
        collection = db.client[db.database_name]["decisions"]
        decision = collection.find_one({"decision_id": decision_id})
        return decision or {}
    except Exception as e:
        print(f"MongoDB error getting decision context: {e}")
        return {}
