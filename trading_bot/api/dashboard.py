from fastapi import APIRouter, HTTPException, Query
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional
import statistics
from collections import defaultdict

# FIXED: Absolute imports
from trading_bot.services.database import db
from trading_bot.services.simulation_engine import simulation_engine
from trading_bot.utils.state_manager import state
from trading_bot.services.outcome_logger import get_recent_outcomes
from trading_bot.models.trade import TradeOutcome

dashboard_router = APIRouter()

async def _ensure_db_connected() -> None:
    """Connect to database if not already connected."""
    if not hasattr(db, '_initialized') or not db._initialized:
        await db.start()
        db._initialized = True

@dashboard_router.get("/status")
async def get_current_status():
    """Get comprehensive current system status"""
    try:
        await _ensure_db_connected()
        current_state = await state.get()

        recent_trades = await db.fetch_recent_trades(limit=100)
        
        trades_24h = len([t for t in recent_trades 
                         if t.get("created_at", datetime.min) > datetime.utcnow() - timedelta(hours=24)])
        
        recent_wins = len([t for t in recent_trades[:trades_24h] if t.get("pnl", 0) > 0])
        win_rate_24h = recent_wins / trades_24h if trades_24h > 0 else 0.0
        
        total_pnl_24h = sum(t.get("pnl", 0) for t in recent_trades[:trades_24h])

        ai_status = {
            "contract_qty": current_state.contract_qty,
            "allowed_directions": current_state.allowed_directions,
            "prompt_profile_id": current_state.prompt_profile_id,
            "hybrid_enabled": current_state.hybrid_enabled,
            "hybrid_threshold": current_state.hybrid_score_threshold
        }

        active_simulations = len(simulation_engine.active_simulations)

        return {
            "system_status": "operational",
            "timestamp": datetime.utcnow().isoformat(),
            "database": {
                "connected": not db.use_memory,
                "type": "memory" if db.use_memory else "mongodb",
                "recent_trades": len(recent_trades),
            },
            "ai_system": ai_status,
            "simulation_engine": {
                "running": current_state.running,
                "active_simulations": active_simulations,
                "last_job_id": current_state.last_sim_job_id,
                "last_error": current_state.last_error
            },
            "performance_24h": {
                "trades": trades_24h,
                "win_rate": round(win_rate_24h, 3),
                "total_pnl": round(total_pnl_24h, 2),
                "avg_pnl_per_trade": round(total_pnl_24h / trades_24h, 2) if trades_24h > 0 else 0.0
            },
            "learning_system": {
                "enabled": True,
                "profile_id": current_state.prompt_profile_id,
                "closed_trades_count": simulation_engine.closed_trades_count,
                "next_update_in": 25 - (simulation_engine.closed_trades_count % 25)
            }
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get status: {str(e)}")


@dashboard_router.get("/metrics")
async def get_performance_metrics(days: int = Query(30, description="Number of days to analyze")):
    """Get comprehensive performance metrics for specified period"""
    try:
        await _ensure_db_connected()
        current_state = await state.get()

        all_trades = await db.fetch_recent_trades(limit=10000)
        
        cutoff_date = datetime.utcnow() - timedelta(days=days)
        period_trades = [t for t in all_trades 
                        if t.get("created_at", datetime.min) > cutoff_date]

        if not period_trades:
            return {
                "period_days": days,
                "overall_performance": {
                    "total_trades": 0,
                    "win_rate": 0.0,
                    "total_pnl": 0.0,
                    "total_pnl_usd": 0.0,
                    "gross_profit": 0.0,
                    "gross_loss": 0.0,
                    "profit_factor": 0.0,
                    "average_trade": 0.0,
                    "largest_win": 0.0,
                    "largest_loss": 0.0
                },
                "session_breakdown": {
                    "AM": {"trades": 0, "win_rate": 0.0, "total_pnl": 0.0},
                    "PM": {"trades": 0, "win_rate": 0.0, "total_pnl": 0.0}
                },
                "direction_analysis": {
                    "long": {"trades": 0, "win_rate": 0.0, "total_pnl": 0.0},
                    "short": {"trades": 0, "win_rate": 0.0, "total_pnl": 0.0}
                },
                "daily_breakdown": [],
                "last_updated": datetime.utcnow().isoformat()
            }

        total_trades = len(period_trades)
        wins = len([t for t in period_trades if t.get("pnl", 0) > 0])
        losses = len([t for t in period_trades if t.get("pnl", 0) < 0])
        win_rate = wins / total_trades if total_trades > 0 else 0.0
        
        pnls = [t.get("pnl", 0) for t in period_trades]
        total_pnl = sum(pnls)
        total_pnl_usd = sum(t.get("pnl_usd", 0) for t in period_trades)
        
        gross_profit = sum(pnl for pnl in pnls if pnl > 0)
        gross_loss = abs(sum(pnl for pnl in pnls if pnl < 0))
        profit_factor = gross_profit / gross_loss if gross_loss > 0 else 0.0
        
        average_trade = total_pnl / total_trades if total_trades > 0 else 0.0
        largest_win = max(pnls) if pnls else 0.0
        largest_loss = abs(min(pnls)) if pnls else 0.0

        am_trades = [t for t in period_trades if t.get("session_label") == "AM"]
        pm_trades = [t for t in period_trades if t.get("session_label") == "PM"]

        def calc_session_metrics(trades):
            if not trades:
                return {"trades": 0, "win_rate": 0.0, "total_pnl": 0.0}
            wins = len([t for t in trades if t.get("pnl", 0) > 0])
            pnl = sum(t.get("pnl", 0) for t in trades)
            return {
                "trades": len(trades),
                "win_rate": wins / len(trades),
                "total_pnl": pnl
            }

        long_trades = [t for t in period_trades if str(t.get("direction", "")).upper() == "LONG"]
        short_trades = [t for t in period_trades if str(t.get("direction", "")).upper() == "SHORT"]

        daily_data = defaultdict(lambda: {"trades": 0, "pnl": 0.0, "wins": 0})
        for trade in period_trades:
            trade_date = trade.get("created_at", datetime.utcnow()).date()
            daily_data[trade_date]["trades"] += 1
            daily_data[trade_date]["pnl"] += trade.get("pnl", 0)
            if trade.get("pnl", 0) > 0:
                daily_data[trade_date]["wins"] += 1

        daily_breakdown = []
        for date, data in sorted(daily_data.items()):
            daily_breakdown.append({
                "date": date.isoformat(),
                "trades": data["trades"],
                "win_rate": data["wins"] / data["trades"] if data["trades"] > 0 else 0.0,
                "total_pnl": data["pnl"]
            })

        profile_outcomes = get_recent_outcomes(current_state.prompt_profile_id, limit=500)
        ai_performance = {
            "recent_decisions": len(profile_outcomes),
            "profile_id": current_state.prompt_profile_id,
            "avg_confidence": 0.0,
            "learning_updates": simulation_engine.closed_trades_count // 25
        }

        return {
            "period_days": days,
            "overall_performance": {
                "total_trades": total_trades,
                "win_rate": round(win_rate, 3),
                "total_pnl": round(total_pnl, 2),
                "total_pnl_usd": round(total_pnl_usd, 2),
                "gross_profit": round(gross_profit, 2),
                "gross_loss": round(gross_loss, 2),
                "profit_factor": round(profit_factor, 2),
                "average_trade": round(average_trade, 2),
                "largest_win": round(largest_win, 2),
                "largest_loss": round(largest_loss, 2)
            },
            "session_breakdown": {
                "AM": calc_session_metrics(am_trades),
                "PM": calc_session_metrics(pm_trades)
            },
            "direction_analysis": {
                "long": calc_session_metrics(long_trades),
                "short": calc_session_metrics(short_trades)
            },
            "daily_breakdown": daily_breakdown[-30:],
            "ai_performance": ai_performance,
            "last_updated": datetime.utcnow().isoformat()
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get metrics: {str(e)}")


@dashboard_router.get("/health")
async def get_system_health():
    """Get detailed system health information"""
    try:
        await _ensure_db_connected()
        current_state = await state.get()
        
        health_status = {
            "overall": "healthy",
            "timestamp": datetime.utcnow().isoformat(),
            "components": {
                "database": {
                    "status": "healthy",
                    "type": "memory" if db.use_memory else "mongodb",
                    "connection": "active",
                },
                "ai_service": {
                    "status": "healthy",
                    "profile_id": current_state.prompt_profile_id,
                    "hybrid_mode": current_state.hybrid_enabled
                },
                "simulation_engine": {
                    "status": "healthy" if not current_state.last_error else "degraded",
                    "running": current_state.running,
                    "active_simulations": len(simulation_engine.active_simulations),
                    "last_error": current_state.last_error
                },
                "learning_system": {
                    "status": "healthy",
                    "closed_trades": simulation_engine.closed_trades_count,
                    "next_update": 25 - (simulation_engine.closed_trades_count % 25)
                }
            }
        }

        component_statuses = [comp["status"] for comp in health_status["components"].values()]
        if "unhealthy" in component_statuses:
            health_status["overall"] = "unhealthy"
        elif "degraded" in component_statuses:
            health_status["overall"] = "degraded"

        return health_status

    except Exception as e:
        return {
            "overall": "unhealthy",
            "timestamp": datetime.utcnow().isoformat(),
            "error": str(e),
            "components": {}
        }
