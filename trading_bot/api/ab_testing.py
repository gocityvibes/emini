# trading_bot/api/ab_testing.py - Complete A/B Testing API

from fastapi import APIRouter, HTTPException, Query
from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta
from collections import defaultdict

from trading_bot.services.database import db
from trading_bot.services.outcome_logger import get_recent_outcomes, get_decision_context
from trading_bot.models.preset_config import ABTestConfiguration, Preset, PRESET_CONFIGURATIONS
from trading_bot.utils.state_manager import state

# Do NOT set a prefix here; app.py includes with prefix="/ab"
router = APIRouter(tags=["ab-testing"])

# Global A/B test storage (in production, this would be in database)
_active_ab_tests: Dict[str, ABTestConfiguration] = {}

async def _ensure_db():
    """Ensure database connection via our DatabaseService."""
    if not hasattr(db, '_initialized') or not getattr(db, '_initialized'):
        await db.start()
        db._initialized = True

@router.post("/start")
async def start_ab_test(test_id: str, preset_a: str, preset_b: str, duration_hours: int = 24):
    """Start a new A/B test comparing two presets"""
    try:
        await _ensure_db()
        if preset_a not in PRESET_CONFIGURATIONS or preset_b not in PRESET_CONFIGURATIONS:
            raise HTTPException(status_code=400, detail="Invalid preset name(s)")

        config = ABTestConfiguration(
            test_id=test_id,
            preset_a=PRESET_CONFIGURATIONS[preset_a],
            preset_b=PRESET_CONFIGURATIONS[preset_b],
            start_time=datetime.utcnow(),
            end_time=datetime.utcnow() + timedelta(hours=duration_hours)
        )
        _active_ab_tests[test_id] = config
        return {"message": f"A/B test {test_id} started", "config": config.dict()}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to start A/B test: {str(e)}")

@router.get("/status")
async def get_ab_test_status(test_id: str):
    """Get current status of an active A/B test"""
    try:
        await _ensure_db()
        config = _active_ab_tests.get(test_id)
        if not config:
            raise HTTPException(status_code=404, detail="A/B test not found")
        
        now = datetime.utcnow()
        remaining = (config.end_time - now).total_seconds()
        
        # Gather performance for both presets
        results = {}
        for label, preset in [("A", config.preset_a), ("B", config.preset_b)]:
            outcomes = get_recent_outcomes(preset.name, limit=500)
            wins = len([o for o in outcomes if o.get("pnl", 0) > 0])
            losses = len([o for o in outcomes if o.get("pnl", 0) < 0])
            total_pnl = sum(o.get("pnl", 0) for o in outcomes)
            results[label] = {
                "preset": preset.name,
                "total_trades": len(outcomes),
                "win_rate": wins / len(outcomes) if outcomes else 0.0,
                "total_pnl": total_pnl
            }
        
        return {
            "test_id": test_id,
            "status": "running" if remaining > 0 else "completed",
            "time_remaining_sec": max(0, remaining),
            "results": results
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get A/B test status: {str(e)}")

@router.post("/stop")
async def stop_ab_test(test_id: str):
    """Stop an active A/B test"""
    try:
        if test_id in _active_ab_tests:
            del _active_ab_tests[test_id]
            return {"message": f"A/B test {test_id} stopped"}
        else:
            raise HTTPException(status_code=404, detail="A/B test not found")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to stop A/B test: {str(e)}")

@router.get("/results")
async def get_ab_test_results(test_id: str):
    """Get final results for a completed A/B test"""
    try:
        await _ensure_db()
        config = _active_ab_tests.get(test_id)
        if not config:
            raise HTTPException(status_code=404, detail="A/B test not found")
        
        # Gather final performance metrics
        results = {}
        for label, preset in [("A", config.preset_a), ("B", config.preset_b)]:
            outcomes = get_recent_outcomes(preset.name, limit=1000)
            wins = len([o for o in outcomes if o.get("pnl", 0) > 0])
            losses = len([o for o in outcomes if o.get("pnl", 0) < 0])
            total_pnl = sum(o.get("pnl", 0) for o in outcomes)
            profit_factor = (sum(o.get("pnl", 0) for o in outcomes if o.get("pnl", 0) > 0) / abs(sum(o.get("pnl", 0) for o in outcomes if o.get("pnl", 0) < 0))) if losses > 0 else float('inf')
            
            results[label] = {
                "preset": preset.name,
                "total_trades": len(outcomes),
                "win_rate": wins / len(outcomes) if outcomes else 0.0,
                "total_pnl": total_pnl,
                "profit_factor": profit_factor
            }
        
        return {
            "test_id": test_id,
            "results": results
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get A/B test results: {str(e)}")
