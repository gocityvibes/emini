# trading_bot/services/ai_prefilter_service.py
from __future__ import annotations

import json
import openai
import hashlib
from typing import Dict, Any, List

from ..config import OPENAI_API_KEY, FT_MODEL_NAME_41, OPENAI_MAX_TOKENS
from .prompt_library import get_profile

# Configure OpenAI
openai.api_key = OPENAI_API_KEY

class PrefilterError(Exception):
    """Raised when prefilter scoring fails"""
    pass

def score_setup(snapshot: dict, profile_id: str, model: str = None) -> dict:
    """
    Score trading setup using fine-tuned GPT-4.1 model.
    
    Returns:
    {
        "score": float(0..100), 
        "label": "pass"|"fail", 
        "rationale": str, 
        "policy_id": str
    }
    """
    if model is None:
        model = FT_MODEL_NAME_41
    
    try:
        # Load prompt profile (same format as main AI)
        profile = get_profile(profile_id)
        policy_id = _generate_policy_id(profile)
        
        # Build messages for scoring
        messages = _build_scoring_messages(snapshot, profile)
        
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
        score_result = json.loads(content)
        
        # Validate and clean response
        validated_score = _validate_score_schema(score_result)
        validated_score["policy_id"] = policy_id
        
        return validated_score
        
    except json.JSONDecodeError as e:
        raise PrefilterError(f"Invalid JSON response from {model}: {e}")
    except openai.OpenAIError as e:
        raise PrefilterError(f"OpenAI API error: {e}")
    except Exception as e:
        raise PrefilterError(f"Prefilter scoring failed: {e}")

def _build_scoring_messages(snapshot: dict, profile: dict) -> List[dict]:
    """Build conversation messages for prefilter scoring"""
    messages = []
    
    # System message for scoring
    system_prompt = """You are a pre-screening system for MES futures scalping setups.

Your job is to quickly score market snapshots for trading potential.

Score from 0-100 based on:
- Trend clarity and momentum
- Volume and volatility
- Support/resistance levels  
- Session timing (AM vs PM)
- Risk/reward potential

Respond with JSON containing:
- score: numeric score 0-100
- label: "pass" if score >= threshold, "fail" otherwise  
- rationale: brief explanation

Focus on filtering out low-probability setups to save processing time."""

    messages.append({"role": "system", "content": system_prompt})
    
    # Add guardrails adapted for scoring
    guardrails = profile.get("guardrails", [])
    if guardrails:
        scoring_rules = [
            "Score 0-30: Poor setups with low probability",
            "Score 31-60: Marginal setups with mixed signals", 
            "Score 61-80: Good setups with clear direction",
            "Score 81-100: Excellent setups with high confidence"
        ]
        guardrails_text = "SCORING GUIDELINES:\n" + "\n".join(f"- {rule}" for rule in scoring_rules)
        messages.append({"role": "system", "content": guardrails_text})
    
    # Add few-shot examples adapted for scoring
    few_shot = profile.get("few_shot", [])
    for example in few_shot[-5:]:  # Use fewer examples for speed
        features = example.get("features", {})
        label = example.get("label", "")
        
        # Convert trade decision to score
        score = 85 if label in ["long", "short"] else 25
        score_label = "pass" if score >= 80 else "fail"
        
        user_example = f"Market snapshot: {json.dumps(features, indent=2)}"
        assistant_example = json.dumps({
            "score": score,
            "label": score_label,
            "rationale": f"Setup shows {label} potential with good momentum and clear direction"
        })
        
        messages.append({"role": "user", "content": user_example})
        messages.append({"role": "assistant", "content": assistant_example})
    
    # Current snapshot for scoring
    current_prompt = f"""
Market snapshot: {json.dumps(snapshot, indent=2)}

Provide your setup score in JSON format with:
- score: numeric score 0-100 (integer)
- label: "pass" or "fail" 
- rationale: brief explanation (string)

Respond only with valid JSON.
"""
    
    messages.append({"role": "user", "content": current_prompt})
    return messages

def _validate_score_schema(score_result: dict) -> dict:
    """Validate and clean the prefilter score"""
    required_fields = ["score", "label", "rationale"]
    
    # Check required fields
    for field in required_fields:
        if field not in score_result:
            raise PrefilterError(f"Missing required field: {field}")
    
    # Validate score
    try:
        score = float(score_result["score"])
        if not (0 <= score <= 100):
            raise PrefilterError(f"Score {score} not in range [0, 100]")
    except (TypeError, ValueError) as e:
        raise PrefilterError(f"Invalid score value: {e}")
    
    # Validate label
    label = score_result["label"].lower()
    if label not in ["pass", "fail"]:
        raise PrefilterError(f"Label '{label}' must be 'pass' or 'fail'")
    
    # Clean and return
    return {
        "score": score,
        "label": label,
        "rationale": str(score_result["rationale"])
    }

def _generate_policy_id(profile: dict) -> str:
    """Generate hash-based policy ID for the prompt profile"""
    profile_str = json.dumps(profile, sort_keys=True)
    return hashlib.md5(profile_str.encode()).hexdigest()[:12]
