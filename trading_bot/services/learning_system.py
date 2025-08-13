# trading_bot/services/learning_system.py
from __future__ import annotations

import json
from typing import Dict, Any, List
from datetime import datetime
from collections import defaultdict

from .outcome_logger import get_recent_outcomes, get_decision_context
from .prompt_library import get_profile, save_profile

class LearningSystemError(Exception):
    """Raised when learning system operations fail"""
    pass

async def update_prompt_profile(profile_id: str, window: int = 500, top_examples: int = 20) -> Dict[str, Any]:
    """
    Update prompt profile based on recent trading outcomes.
    
    - Read last `window` outcomes for profile_id
    - Curate `top_examples` wins with clear rationale → refresh `few_shot`
    - Adjust weights: long_bias/short_bias small steps, clamp [-1.0, +1.0]
    - Add/remove guardrails for recurring loss patterns
    - Save via prompt_library.save_profile()
    - Return summary dict (counts, winrate, updated_at)
    """
    try:
        # Get recent outcomes and decisions
        recent_outcomes = get_recent_outcomes(profile_id, window)
        
        if not recent_outcomes:
            return {
                "profile_id": profile_id,
                "outcomes_analyzed": 0,
                "win_rate": 0.0,
                "updated_at": datetime.utcnow().isoformat(),
                "changes": "No outcomes to analyze"
            }
        
        # Enrich outcomes with decision context
        enriched_outcomes = []
        for outcome in recent_outcomes:
            decision_id = outcome.get("decision_id")
            if decision_id:
                decision_context = get_decision_context(decision_id)
                if decision_context:
                    enriched_outcomes.append({
                        "outcome": outcome,
                        "decision": decision_context
                    })
        
        # Calculate performance metrics
        win_count = len([o for o in enriched_outcomes if o["outcome"].get("result") == "win"])
        total_count = len(enriched_outcomes)
        win_rate = win_count / total_count if total_count > 0 else 0.0
        
        # Get current profile
        current_profile = get_profile(profile_id)
        
        # Update few-shot examples
        updated_few_shot = _update_few_shot_examples(enriched_outcomes, top_examples)
        
        # Update weights based on performance
        updated_weights = _update_weights(enriched_outcomes, current_profile.get("weights", {}))
        
        # Update guardrails based on loss patterns
        updated_guardrails = _update_guardrails(enriched_outcomes, current_profile.get("guardrails", []))
        
        # Create updated profile
        updated_profile = current_profile.copy()
        updated_profile["few_shot"] = updated_few_shot
        updated_profile["weights"] = updated_weights
        updated_profile["guardrails"] = updated_guardrails
        updated_profile["updated_at"] = datetime.utcnow().isoformat()
        
        # Save updated profile
        save_profile(profile_id, updated_profile)
        
        return {
            "profile_id": profile_id,
            "outcomes_analyzed": total_count,
            "win_rate": win_rate,
            "few_shot_examples": len(updated_few_shot),
            "weights_updated": updated_weights,
            "guardrails_count": len(updated_guardrails),
            "updated_at": updated_profile["updated_at"],
            "changes": f"Updated {len(updated_few_shot)} examples, adjusted weights, {len(updated_guardrails)} guardrails"
        }
        
    except Exception as e:
        raise LearningSystemError(f"Failed to update prompt profile {profile_id}: {e}")

def _update_few_shot_examples(enriched_outcomes: List[Dict], top_examples: int) -> List[Dict]:
    """Update few-shot examples with best performing trades"""
    
    # Filter winning trades with good reasoning
    good_wins = []
    for item in enriched_outcomes:
        outcome = item["outcome"]
        decision = item["decision"]
        
        if (outcome.get("result") == "win" and 
            decision.get("confidence", 0) >= 0.7 and
            decision.get("reasoning") and
            len(decision.get("reasoning", "")) > 20):  # Non-trivial reasoning
            
            # Create few-shot example
            example = {
                "snapshot_hash": decision.get("snapshot_hash", ""),
                "features": _extract_features_from_decision(decision),
                "label": decision.get("direction", ""),
                "rationale": decision.get("reasoning", "")
            }
            good_wins.append(example)
    
    # Sort by confidence and take top examples
    good_wins.sort(key=lambda x: x.get("confidence", 0), reverse=True)
    return good_wins[:top_examples]

def _extract_features_from_decision(decision: Dict) -> Dict:
    """Extract market features from decision context"""
    # This would ideally extract the original snapshot features
    # For now, create simplified features from available data
    return {
        "current_price": decision.get("entry", 5100),
        "direction": decision.get("direction", ""),
        "confidence": decision.get("confidence", 0.5),
        "session": decision.get("session", "AM"),
        "market_condition": decision.get("market_condition", "mixed")
    }

def _update_weights(enriched_outcomes: List[Dict], current_weights: Dict) -> Dict:
    """Update directional bias weights based on performance"""
    
    # Initialize weights if not present
    weights = {
        "long_bias": current_weights.get("long_bias", 0.0),
        "short_bias": current_weights.get("short_bias", 0.0),
        "risk": current_weights.get("risk", 1.0)
    }
    
    # Analyze directional performance
    long_trades = [item for item in enriched_outcomes if item["decision"].get("direction") == "long"]
    short_trades = [item for item in enriched_outcomes if item["decision"].get("direction") == "short"]
    
    # Calculate win rates
    long_wins = len([t for t in long_trades if t["outcome"].get("result") == "win"])
    long_win_rate = long_wins / len(long_trades) if long_trades else 0.5
    
    short_wins = len([t for t in short_trades if t["outcome"].get("result") == "win"])
    short_win_rate = short_wins / len(short_trades) if short_trades else 0.5
    
    # Adjust bias (small steps)
    step_size = 0.05
    
    if long_win_rate > 0.65:  # Good long performance
        weights["long_bias"] = min(1.0, weights["long_bias"] + step_size)
    elif long_win_rate < 0.45:  # Poor long performance
        weights["long_bias"] = max(-1.0, weights["long_bias"] - step_size)
    
    if short_win_rate > 0.65:  # Good short performance
        weights["short_bias"] = min(1.0, weights["short_bias"] + step_size)
    elif short_win_rate < 0.45:  # Poor short performance
        weights["short_bias"] = max(-1.0, weights["short_bias"] - step_size)
    
    # Adjust risk based on overall performance
    total_outcomes = len(enriched_outcomes)
    total_wins = len([item for item in enriched_outcomes if item["outcome"].get("result") == "win"])
    overall_win_rate = total_wins / total_outcomes if total_outcomes else 0.5
    
    if overall_win_rate > 0.70:  # Excellent performance, can take more risk
        weights["risk"] = min(1.2, weights["risk"] + 0.05)
    elif overall_win_rate < 0.50:  # Poor performance, reduce risk
        weights["risk"] = max(0.8, weights["risk"] - 0.05)
    
    return weights

def _update_guardrails(enriched_outcomes: List[Dict], current_guardrails: List[str]) -> List[str]:
    """Update guardrails based on loss patterns"""
    
    guardrails = current_guardrails.copy()
    
    # Analyze loss patterns
    losses = [item for item in enriched_outcomes if item["outcome"].get("result") == "loss"]
    
    if not losses:
        return guardrails
    
    # Pattern analysis
    loss_patterns = defaultdict(int)
    
    for loss_item in losses:
        decision = loss_item["decision"]
        outcome = loss_item["outcome"]
        
        # Low confidence losses
        if decision.get("confidence", 0) < 0.6:
            loss_patterns["low_confidence"] += 1
        
        # Session-based losses
        session = decision.get("session", "")
        if session:
            loss_patterns[f"{session}_session"] += 1
        
        # Market condition losses
        condition = decision.get("market_condition", "")
        if condition:
            loss_patterns[f"{condition}_condition"] += 1
        
        # Quick losses (under 60 seconds)
        duration = outcome.get("duration_s", 0)
        if duration < 60:
            loss_patterns["quick_loss"] += 1
    
    # Add new guardrails based on significant patterns
    total_losses = len(losses)
    threshold = max(3, total_losses * 0.3)  # At least 3 or 30% of losses
    
    new_guardrails = []
    
    if loss_patterns["low_confidence"] >= threshold:
        if "Minimum confidence 0.75 for trade execution" not in guardrails:
            new_guardrails.append("Minimum confidence 0.75 for trade execution")
    
    if loss_patterns["quick_loss"] >= threshold:
        if "Avoid trades in highly volatile conditions" not in guardrails:
            new_guardrails.append("Avoid trades in highly volatile conditions")
    
    if loss_patterns["AM_session"] >= threshold and loss_patterns["AM_session"] > loss_patterns.get("PM_session", 0):
        if "Exercise extra caution during AM session" not in guardrails:
            new_guardrails.append("Exercise extra caution during AM session")
    
    if loss_patterns["chop_condition"] >= threshold:
        if "Avoid trading in choppy market conditions" not in guardrails:
            new_guardrails.append("Avoid trading in choppy market conditions")
    
    # Remove outdated guardrails if performance improves
    recent_win_rate = len([item for item in enriched_outcomes[-50:] if item["outcome"].get("result") == "win"]) / min(50, len(enriched_outcomes))
    if recent_win_rate > 0.70:
        # Remove restrictive guardrails if doing well
        restrictive_phrases = ["Exercise extra caution", "Avoid trades in"]
        guardrails = [g for g in guardrails if not any(phrase in g for phrase in restrictive_phrases)]
    
    return guardrails + new_guardrails

async def apply_learning_update(patterns: Dict[str, Any]) -> Dict[str, Any]:
    """Apply a manual learning update (for admin API)"""
    try:
        profile_id = patterns.get("profile_id", "default")
        
        if patterns.get("startup"):
            # Startup initialization
            return {
                "status": "initialized",
                "profile_id": profile_id,
                "message": "Learning system ready"
            }
        
        # Manual update
        result = await update_prompt_profile(profile_id)
        return {
            "status": "success",
            "result": result
        }
        
    except Exception as e:
        raise LearningSystemError(f"Apply learning update failed: {e}")

def extract_learning_patterns(trades: List[Dict], config: Dict = None) -> Dict[str, Any]:
    """Extract learning patterns from completed trades (backward compatibility)"""
    if not trades:
        return {"patterns": [], "insights": "No trades to analyze"}
    
    # Simple pattern extraction
    total_trades = len(trades)
    wins = len([t for t in trades if t.get("pnl", 0) > 0])
    win_rate = wins / total_trades if total_trades > 0 else 0.0
    
    patterns = []
    
    if win_rate > 0.70:
        patterns.append("High success rate detected")
    elif win_rate < 0.50:
        patterns.append("Low success rate - review strategy")
    
    # Direction analysis
    long_trades = [t for t in trades if t.get("direction", "").lower() == "long"]
    short_trades = [t for t in trades if t.get("direction", "").lower() == "short"]
    
    if len(long_trades) > len(short_trades) * 2:
        patterns.append("Strong long bias in recent trades")
    elif len(short_trades) > len(long_trades) * 2:
        patterns.append("Strong short bias in recent trades")
    
    return {
        "patterns": patterns,
        "total_trades": total_trades,
        "win_rate": win_rate,
        "insights": f"Analyzed {total_trades} trades with {win_rate:.1%} win rate"
    }
