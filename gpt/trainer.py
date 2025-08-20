"""
GPT Trading Trainer
Interfaces with GPT for trade decisions with structured prompts and validation.
"""

import json
from typing import Dict, List, Optional, NamedTuple
from dataclasses import dataclass
from datetime import datetime
import openai
from tenacity import retry, stop_after_attempt, wait_exponential


@dataclass
class GPTDecision:
    """Structured GPT trading decision."""
    decision: str  # 'trade' or 'skip'
    direction: str  # 'long' or 'short' (if trading)
    named_setup: str  # Setup name from GPT
    confluences: List[str]  # List of confluence factors
    confidence: int  # 0-100 confidence score
    rationale: str  # GPT's reasoning
    raw_response: str  # Full GPT response for debugging
    processing_time_ms: int  # Time taken to get response


class GPTTrainer:
    """
    GPT integration for trade decision making with structured prompts.
    
    Features:
    - Structured decision contract with validation
    - Confidence scoring and calibration
    - Setup naming and confluence identification
    - Error handling and retry logic
    - Response time tracking
    """
    
    def __init__(self, config: Dict, api_key: str):
        """
        Initialize GPT trainer.
        
        Args:
            config: System configuration
            api_key: OpenAI API key
        """
        self.config = config
        self.gpt_config = config['gpt']
        self.confidence_min = self.gpt_config['confidence_min']
        
        # Initialize OpenAI client
        openai.api_key = api_key
        self.model = "gpt-4"  # Use GPT-4 for best decision quality
        
        # System prompt for consistent behavior
        self.system_prompt = self._build_system_prompt()
    
    def _build_system_prompt(self) -> str:
        """Build comprehensive system prompt for GPT."""
        return """You are an expert MES (E-mini S&P 500) futures scalping analyst. Your job is to evaluate trading candidates and make precise trade/skip decisions.

TRADING RULES (MUST FOLLOW):
- Only trade during RTH sessions: 08:30-10:30 CT and 13:00-15:00 CT
- Only these 3 setups: ORB retest-go, 20EMA pullback, VWAP rejection
- Volume must be ≥1.8x average (≥2.2x for ORB)
- ATR must be 0.8-2.0 points
- Target: +1.25 points, Stop: -0.75 points
- Move to breakeven at +0.50, trail by 0.50 after +1.00

RESPONSE FORMAT (JSON):
{
    "decision": "trade" or "skip",
    "direction": "long" or "short" (if trading),
    "named_setup": "ORB_retest_go" or "20EMA_pullback" or "VWAP_rejection",
    "confluences": ["factor1", "factor2", ...],
    "confidence": 85-100,
    "rationale": "detailed reasoning"
}

CONFLUENCE FACTORS TO CONSIDER:
- Multi-timeframe EMA alignment
- Volume expansion vs average
- Clean price action/momentum
- VWAP positioning
- ATR in optimal range
- Setup clarity and strength
- Risk/reward favorability

CONFIDENCE SCORING:
- 85-89: Good setup with minor concerns
- 90-94: Strong setup with clear confluences  
- 95-100: Exceptional setup with multiple confluences

You must be selective. Only recommend trades with ≥85% confidence and clear edge."""
    
    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=4, max=10))
    def evaluate_candidate(self, candidate_data: Dict) -> GPTDecision:
        """
        Evaluate trading candidate with GPT.
        
        Args:
            candidate_data: Complete candidate information
            
        Returns:
            GPTDecision object with structured result
        """
        start_time = datetime.now()
        
        # Build user prompt with candidate data
        user_prompt = self._build_user_prompt(candidate_data)
        
        try:
            # Call GPT
            response = openai.ChatCompletion.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": self.system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                max_tokens=500,
                temperature=0.3,  # Low temperature for consistent decisions
                response_format={"type": "json_object"}
            )
            
            # Parse response
            raw_response = response.choices[0].message.content
            decision_data = json.loads(raw_response)
            
            # Validate and structure response
            decision = self._validate_and_structure_response(
                decision_data, candidate_data, raw_response
            )
            
            # Calculate processing time
            processing_time = int((datetime.now() - start_time).total_seconds() * 1000)
            decision.processing_time_ms = processing_time
            
            return decision
            
        except json.JSONDecodeError as e:
            return self._create_error_decision(f"Invalid JSON response: {e}", candidate_data)
        except Exception as e:
            return self._create_error_decision(f"GPT API error: {e}", candidate_data)
    
    def _build_user_prompt(self, candidate_data: Dict) -> str:
        """Build detailed user prompt with candidate information."""
        candidate = candidate_data['candidate']
        
        prompt = f"""TRADING CANDIDATE ANALYSIS

SETUP DETAILS:
- Setup Type: {candidate.setup_type}
- Direction: {candidate.direction}
- Current Price: {candidate.current_price:.2f}
- Prefilter Score: {candidate.prefilter_score:.1f}/100

MARKET CONDITIONS:
- Session: {candidate.session_label}
- Volume Multiple: {candidate.volume_multiple:.1f}x
- ATR (5m): {candidate.atr_5m:.2f}
- EMA Alignment: {candidate.ema_alignment}
- VWAP Distance: {candidate.vwap_distance:+.2f}

STRUCTURE:
{candidate.structure_notes}

CONFIDENCE FACTORS:
{', '.join(candidate.confidence_factors) if candidate.confidence_factors else 'None identified'}

RISK FACTORS:
{', '.join(candidate.risk_factors) if candidate.risk_factors else 'None identified'}

TIMEFRAME INDICATORS:
{self._format_indicators(candidate_data.get('indicators', {}))}

Evaluate this candidate and provide your decision in the required JSON format."""
        
        return prompt
    
    def _format_indicators(self, indicators: Dict) -> str:
        """Format indicator data for prompt."""
        lines = []
        
        if '1m_EMA_20' in indicators:
            lines.append(f"1m EMA20: {indicators['1m_EMA_20']:.2f}")
        if '5m_EMA_20' in indicators:
            lines.append(f"5m EMA20: {indicators['5m_EMA_20']:.2f}")
        if '15m_EMA_20' in indicators:
            lines.append(f"15m EMA20: {indicators['15m_EMA_20']:.2f}")
        if '1m_VWAP' in indicators:
            lines.append(f"VWAP: {indicators['1m_VWAP']:.2f}")
        if '1m_RSI_14' in indicators:
            lines.append(f"RSI: {indicators['1m_RSI_14']:.1f}")
        
        return '\n'.join(lines) if lines else 'Limited indicator data'
    
    def _validate_and_structure_response(self, 
                                       decision_data: Dict, 
                                       candidate_data: Dict,
                                       raw_response: str) -> GPTDecision:
        """
        Validate GPT response and create structured decision.
        
        Args:
            decision_data: Parsed JSON from GPT
            candidate_data: Original candidate information
            raw_response: Raw GPT response text
            
        Returns:
            Validated GPTDecision object
        """
        # Extract fields with defaults
        decision = decision_data.get('decision', 'skip').lower()
        direction = decision_data.get('direction', '').lower()
        named_setup = decision_data.get('named_setup', 'unknown')
        confluences = decision_data.get('confluences', [])
        confidence = decision_data.get('confidence', 0)
        rationale = decision_data.get('rationale', 'No rationale provided')
        
        # Validation checks
        if decision not in ['trade', 'skip']:
            decision = 'skip'
        
        if decision == 'trade':
            if direction not in ['long', 'short']:
                direction = candidate_data['candidate'].direction
            
            # Validate setup name
            valid_setups = ['ORB_retest_go', '20EMA_pullback', 'VWAP_rejection']
            if named_setup not in valid_setups:
                named_setup = candidate_data['candidate'].setup_type
        
        # Validate confidence
        if not isinstance(confidence, (int, float)) or confidence < 0 or confidence > 100:
            confidence = 0
        
        # Ensure confluences is a list
        if not isinstance(confluences, list):
            confluences = []
        
        # Gate decision based on confidence threshold
        if decision == 'trade' and confidence < self.confidence_min:
            decision = 'skip'
            rationale += f" [Gated: confidence {confidence} < minimum {self.confidence_min}]"
        
        # Gate based on prefilter score
        prefilter_score = candidate_data['candidate'].prefilter_score
        if decision == 'trade' and prefilter_score < self.config['prefilter']['min_score']:
            decision = 'skip'
            rationale += f" [Gated: prefilter score {prefilter_score} < minimum {self.config['prefilter']['min_score']}]"
        
        return GPTDecision(
            decision=decision,
            direction=direction,
            named_setup=named_setup,
            confluences=confluences,
            confidence=int(confidence),
            rationale=rationale,
            raw_response=raw_response,
            processing_time_ms=0  # Will be set by caller
        )
    
    def _create_error_decision(self, error_msg: str, candidate_data: Dict) -> GPTDecision:
        """Create error decision when GPT fails."""
        return GPTDecision(
            decision='skip',
            direction='',
            named_setup='error',
            confluences=[],
            confidence=0,
            rationale=f"Error: {error_msg}",
            raw_response='',
            processing_time_ms=0
        )
    
    def batch_evaluate_candidates(self, candidates: List[Dict]) -> List[GPTDecision]:
        """
        Evaluate multiple candidates in sequence.
        
        Args:
            candidates: List of candidate data dicts
            
        Returns:
            List of GPTDecision objects
        """
        decisions = []
        
        for candidate_data in candidates:
            try:
                decision = self.evaluate_candidate(candidate_data)
                decisions.append(decision)
            except Exception as e:
                error_decision = self._create_error_decision(str(e), candidate_data)
                decisions.append(error_decision)
        
        return decisions
    
    def validate_decision_contract(self, decision: GPTDecision) -> Dict[str, bool]:
        """
        Validate that decision meets all contract requirements.
        
        Args:
            decision: GPTDecision to validate
            
        Returns:
            Dict with validation results
        """
        checks = {}
        
        # Decision field validation
        checks['valid_decision'] = decision.decision in ['trade', 'skip']
        
        # If trading, validate required fields
        if decision.decision == 'trade':
            checks['valid_direction'] = decision.direction in ['long', 'short']
            checks['valid_setup'] = decision.named_setup in [
                'ORB_retest_go', '20EMA_pullback', 'VWAP_rejection'
            ]
            checks['has_confluences'] = len(decision.confluences) > 0
            checks['sufficient_confidence'] = decision.confidence >= self.confidence_min
        else:
            checks['valid_direction'] = True
            checks['valid_setup'] = True
            checks['has_confluences'] = True
            checks['sufficient_confidence'] = True
        
        # General validation
        checks['confidence_in_range'] = 0 <= decision.confidence <= 100
        checks['has_rationale'] = len(decision.rationale.strip()) > 0
        
        # Overall validation
        checks['contract_valid'] = all(checks.values())
        
        return checks
    
    def get_decision_summary(self, decision: GPTDecision) -> Dict:
        """
        Get human-readable summary of GPT decision.
        
        Args:
            decision: GPTDecision object
            
        Returns:
            Dict with formatted summary
        """
        summary = {
            'action': decision.decision.upper(),
            'setup': decision.named_setup,
            'confidence': f"{decision.confidence}%",
            'key_factors': decision.confluences[:3],  # Top 3 confluences
            'processing_time': f"{decision.processing_time_ms}ms",
            'meets_threshold': decision.confidence >= self.confidence_min
        }
        
        if decision.decision == 'trade':
            summary['direction'] = decision.direction.upper()
            summary['risk_reward'] = "1.25:0.75 (1.67:1)"
        
        return summary


# Decision contract specification and examples:
"""
GPT Decision Contract:

INPUT (candidate_data):
{
    'candidate': TradingCandidate object,
    'indicators': dict with technical indicators,
    'session_info': dict with session validation,
    'timestamp': datetime
}

OUTPUT (GPTDecision):
{
    decision: 'trade' or 'skip',
    direction: 'long' or 'short' (if trading),
    named_setup: 'ORB_retest_go' or '20EMA_pullback' or 'VWAP_rejection',
    confluences: ['strong_trend', 'high_volume', 'clean_structure'],
    confidence: 85-100,
    rationale: "Detailed reasoning for decision",
    raw_response: "Full GPT response",
    processing_time_ms: 1250
}

Gating Rules:
✓ Accept only if prefilter_score ≥ 75
✓ Accept only if confidence ≥ confidence_min (85, adaptive 82-92)
✓ Require named setup from approved list
✓ Require confluences list for trade decisions

Error Handling:
- API timeouts → skip with error rationale
- Invalid JSON → skip with parse error
- Missing required fields → skip with validation error
- Network errors → retry with exponential backoff

Example GPT Response:
{
    "decision": "trade",
    "direction": "long", 
    "named_setup": "ORB_retest_go",
    "confluences": [
        "multi_timeframe_trend_alignment",
        "high_volume_expansion_2.3x",
        "clean_price_rejection_at_orb_high",
        "optimal_atr_range"
    ],
    "confidence": 88,
    "rationale": "Strong ORB retest setup with 2.3x volume expansion and clean rejection at key level. All timeframes aligned bullish with optimal volatility conditions. Clear risk/reward at 1.67:1."
}

Common Confluence Factors GPT Should Identify:
- multi_timeframe_ema_alignment
- high_volume_expansion_vs_average  
- clean_price_action_momentum
- optimal_atr_volatility_range
- clear_setup_structure
- favorable_risk_reward_ratio
- session_timing_optimal
- vwap_positioning_supportive
- confluence_of_technical_levels
- institutional_order_flow_hints

Processing Time Targets:
- Target: <2000ms per decision
- Acceptable: <5000ms
- Timeout: >10000ms → retry or skip
"""