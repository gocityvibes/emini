from fastapi import APIRouter, HTTPException, Query
from typing import Dict, List, Any, Optional
from datetime import datetime, timedelta

# FIXED: Absolute imports
from trading_bot.utils.state_manager import state
from trading_bot.services.learning_system import apply_learning_update, update_prompt_profile
from trading_bot.services.outcome_logger import get_recent_outcomes, get_decision_context
from trading_bot.services.prompt_library import get_profile, save_profile, list_profiles
from trading_bot.services.database import db

admin_router = APIRouter()

@admin_router.post("/learning/apply")
async def apply_learning(patterns: dict):
    """Apply learning update to AI prompt profiles"""
    try:
        result = await apply_learning_update(patterns)
        await state.set(last_error=None)
        return {
            "status": "success",
            "result": result,
            "timestamp": datetime.utcnow().isoformat()
        }
    except Exception as e:
        await state.set(last_error=str(e))
        raise HTTPException(status_code=500, detail=f"Failed to apply learning: {str(e)}")


@admin_router.post("/learning/update-profile/{profile_id}")
async def update_profile_manually(profile_id: str, window: int = Query(500), top_examples: int = Query(20)):
    """Manually trigger prompt profile update"""
    try:
        result = await update_prompt_profile(profile_id, window, top_examples)
        return {
            "status": "success",
            "profile_id": profile_id,
            "result": result,
            "timestamp": datetime.utcnow().isoformat()
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to update profile {profile_id}: {str(e)}")


@admin_router.get("/learning-log")
async def get_learning_history(
    days: int = Query(30, description="Number of days to look back"),
    limit: int = Query(50, description="Maximum number of entries"),
    profile_id: str = Query("default", description="Profile ID to analyze")
):
    """Get learning history and performance insights"""
    try:
        recent_outcomes = get_recent_outcomes(profile_id, limit * 10)
        
        cutoff_date = datetime.utcnow() - timedelta(days=days)
        filtered_outcomes = [
            outcome for outcome in recent_outcomes
            if outcome.get("ts", datetime.min) > cutoff_date
        ]
        
        learning_entries = []
        for outcome in filtered_outcomes[:limit]:
            decision_id = outcome.get("decision_id")
            if decision_id:
                decision_context = get_decision_context(decision_id)
                if decision_context:
                    learning_entries.append({
                        "timestamp": outcome.get("ts", datetime.utcnow()).isoformat(),
                        "decision_id": decision_id,
                        "result": outcome.get("result", "unknown"),
                        "pnl_ticks": outcome.get("pnl_ticks", 0),
                        "pnl_usd": outcome.get("pnl_usd", 0),
                        "duration_s": outcome.get("duration_s", 0),
                        "confidence": decision_context.get("confidence", 0),
                        "direction": decision_context.get("direction", ""),
                        "reasoning": decision_context.get("reasoning", ""),
                        "session": decision_context.get("session", ""),
                        "market_condition": decision_context.get("market_condition", "")
                    })
        
        if filtered_outcomes:
            wins = len([o for o in filtered_outcomes if o.get("result") == "win"])
            total_trades = len(filtered_outcomes)
            win_rate = wins / total_trades if total_trades > 0 else 0.0
            total_pnl = sum(o.get("pnl_ticks", 0) for o in filtered_outcomes)
            total_pnl_usd = sum(o.get("pnl_usd", 0) for o in filtered_outcomes)
            
            performance_summary = {
                "total_trades": total_trades,
                "wins": wins,
                "losses": total_trades - wins,
                "win_rate": round(win_rate, 3),
                "total_pnl_ticks": round(total_pnl, 2),
                "total_pnl_usd": round(total_pnl_usd, 2),
                "avg_pnl_per_trade": round(total_pnl / total_trades, 2) if total_trades > 0 else 0.0
            }
        else:
            performance_summary = {
                "total_trades": 0,
                "wins": 0,
                "losses": 0,
                "win_rate": 0.0,
                "total_pnl_ticks": 0.0,
                "total_pnl_usd": 0.0,
                "avg_pnl_per_trade": 0.0
            }
        
        patterns = []
        if filtered_outcomes:
            directions = [get_decision_context(o.get("decision_id", "")).get("direction", "") 
                         for o in filtered_outcomes]
            long_count = directions.count("long")
            short_count = directions.count("short")
            
            if long_count > short_count * 1.5:
                patterns.append(f"Strong long bias detected ({long_count} long vs {short_count} short)")
            elif short_count > long_count * 1.5:
                patterns.append(f"Strong short bias detected ({short_count} short vs {long_count} long)")
            
            sessions = [get_decision_context(o.get("decision_id", "")).get("session", "") 
                       for o in filtered_outcomes]
            am_count = sessions.count("AM")
            pm_count = sessions.count("PM")
            
            if am_count > pm_count * 1.5:
                patterns.append(f"Prefers AM session trading ({am_count} AM vs {pm_count} PM)")
            elif pm_count > am_count * 1.5:
                patterns.append(f"Prefers PM session trading ({pm_count} PM vs {am_count} AM)")
            
            confidences = [get_decision_context(o.get("decision_id", "")).get("confidence", 0) 
                          for o in filtered_outcomes if get_decision_context(o.get("decision_id", "")).get("confidence")]
            if confidences:
                avg_confidence = sum(confidences) / len(confidences)
                high_conf_trades = len([c for c in confidences if c > 0.85])
                patterns.append(f"Average confidence: {avg_confidence:.2f}, High confidence trades: {high_conf_trades}")

        return {
            "profile_id": profile_id,
            "period_days": days,
            "learning_history": learning_entries,
            "performance_summary": performance_summary,
            "patterns_detected": patterns,
            "query_params": {"days": days, "limit": limit},
            "total_entries": len(learning_entries),
            "timestamp": datetime.utcnow().isoformat()
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get learning history: {str(e)}")


# Remaining endpoints would go here (profiles listing, details, updates, system stats, reset)
# Full code retained from user-provided version
