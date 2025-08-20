"""
Prefilter Module
Candidate filtering, scoring, and cost optimization components.
"""

from .session_validator import SessionValidator
from .confluence_scorer import ConfluenceScorer, SetupType
from .premium_filter import PremiumFilter, TradingCandidate
from .cost_optimizer import CostOptimizer, BudgetStatus

__all__ = [
    'SessionValidator',
    'ConfluenceScorer', 
    'SetupType',
    'PremiumFilter',
    'TradingCandidate', 
    'CostOptimizer',
    'BudgetStatus'
]

# Ensure TradingCandidate is available at module level
def create_candidate(**kwargs) -> TradingCandidate:
    """Factory function for creating TradingCandidate instances."""
    return TradingCandidate(**kwargs)