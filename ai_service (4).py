# trading_bot/services/ai_service.py
from __future__ import annotations

import json
import openai
import hashlib
from typing import Dict, Any, List
from datetime import datetime

from ..config import OPENAI_API_KEY, MODEL_NAME, OPENAI_MAX_TOKENS, OPENAI_CONCURRENCY
from .prompt_library import get_profile

# Configure OpenAI
openai.api_key = OPENAI_API_KEY

class AIDecisionError(Exception):
    """Raised when AI decision is invalid or fails"""
    pass

def get_trade_decision(
    snapshot: dict,
    constraints: dict,  # {"allowed_directions": ["long","short"]}
    profile_id: str,
    model: str = MODEL_NAME
) -> dict:
    """
    Get GPT-5 trade decision with strict schema validation.
    
    Returns schema:
    {
      "direction": "long" | "short",
      "entry": float,
      "sl": float,
      "tp": float,
      "confidence": float,   # 0..1
      "reasoning": str,
      "policy_id": str       # prompt profile version/hash
    }
    """
    try:
        # Load prompt profile
        profile = get_profile(profile_id)
        policy_id = _generate_policy_id(profile)
        
        # Build messages
        messages = _build_messages(snapshot, constraints, profile)
        
        # Make OpenAI API call
        response = openai.chat.completions.create(
            model=model,
            messages=messages,
            max_tokens=OPENAI_MAX_TOKENS,
            temperature=0.1,
            response_format={"type": "json_object"}
        )
        
        # Parse and validate response
        content = response.choices[0].message.content
        decision = json.loads(content)
        
        # Validate schema
        validated_decision = _validate_decision_schema(decision, constraints)
        validated_decision["policy_id"] = policy_id
        
        return validated_decision
        
    except json.JSONDecodeError as e:
        raise AIDecisionError(f"Invalid JSON response from {model}: {e}")
    except openai.OpenAIError as e:
        raise AIDecisionError(f"OpenAI API error: {e}")
    except Exception as e:
        raise AIDecisionError(f"AI decision failed: {e}")

def _build_messages(snapshot: dict, constraints: dict, profile: dict) -> List[dict]:
    """Build conversation messages for GPT-5"""
    messages = []
    
    # System message
    system_prompt = profile.get("system", "You are a professional MES futures scalping trader.")
    messages.append({"role": "system", "content": system_prompt})
    
    # Add guardrails
    guardrails = profile.get("guardrails", [])
    if guardrails:
        guardrails_text = "HARD CONSTRAINTS:\n" + "\n".join(f"- {rule}" for rule in guardrails)
        messages.append({"role": "system", "content": guardrails_text})
    
    # Add few-shot examples
    few_shot = profile.get("few_shot", [])
    for example in few_shot[-10:]:  # Use last 10 examples
        features = example.get("features", {})
        label = example.get("label", "")
        rationale = example.get("rationale", "")
        
        user_example = f"Market snapshot: {json.dumps(features, indent=2, default=str)}"
        assistant_example = json.dumps({
            "direction": label,
            "entry": features.get("current_price", 5000),
            "sl": features.get("suggested_sl", 5000),
            "tp": features.get("suggested_tp", 5000),
            "confidence": 0.85,
            "reasoning": rationale
        })
        
        messages.append({"role": "user", "content": user_example})
        messages.append({"role": "assistant", "content": assistant_example})
    
    # Current snapshot and constraints
    weights = profile.get("weights", {})
    current_prompt = f"""
Market snapshot: {json.dumps(snapshot, indent=2, default=str)}

Constraints:
- Allowed directions: {constraints.get('allowed_directions', ['long', 'short'])}
- Current weights: {weights}

Provide your trading decision in JSON format with:
- direction: "long" or "short" (must be in allowed directions)
- entry: entry price (float)
- sl: stop loss price (float) 
- tp: take profit price (float)
- confidence: confidence score 0.0-1.0 (float)
- reasoning: brief explanation (string)

Respond only with valid JSON.
"""
    
    messages.append({"role": "user", "content": current_prompt})
    return messages

def _validate_decision_schema(decision: dict, constraints: dict) -> dict:
    """Validate and clean the AI decision"""
    required_fields = ["direction", "entry", "sl", "tp", "confidence", "reasoning"]
    
    # Check required fields
    for field in required_fields:
        if field not in decision:
            raise AIDecisionError(f"Missing required field: {field}")
    
    # Validate direction constraint
    allowed_directions = constraints.get("allowed_directions", ["long", "short"])
    if decision["direction"] not in allowed_directions:
        raise AIDecisionError(f"Direction '{decision['direction']}' not in allowed: {allowed_directions}")
    
    # Validate numeric fields
    try:
        entry = float(decision["entry"])
        sl = float(decision["sl"])
        tp = float(decision["tp"])
        confidence = float(decision["confidence"])
    except (TypeError, ValueError) as e:
        raise AIDecisionError(f"Invalid numeric values: {e}")
    
    # Validate confidence range
    if not (0.0 <= confidence <= 1.0):
        raise AIDecisionError(f"Confidence {confidence} not in range [0.0, 1.0]")
    
    # Validate price logic
    if decision["direction"] == "long":
        if not (sl < entry < tp):
            raise AIDecisionError(f"Long trade: SL({sl}) < Entry({entry}) < TP({tp}) not satisfied")
    else:  # short
        if not (tp < entry < sl):
            raise AIDecisionError(f"Short trade: TP({tp}) < Entry({entry}) < SL({sl}) not satisfied")
    
    # Clean and return
    return {
        "direction": decision["direction"],
        "entry": entry,
        "sl": sl,
        "tp": tp,
        "confidence": confidence,
        "reasoning": str(decision["reasoning"])
    }

def _generate_policy_id(profile: dict) -> str:
    """Generate hash-based policy ID for the prompt profile"""
    profile_str = json.dumps(profile, sort_keys=True)
    return hashlib.md5(profile_str.encode()).hexdigest()[:12]
