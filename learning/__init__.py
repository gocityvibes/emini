"""
Learning Module
Feedback loops, hard negatives, and pattern memory components.
"""

from .feedback_loop import FeedbackLoop, TradeRecord, TradeOutcome
from .hard_negatives import HardNegatives, NoTradeTemplate
from .pattern_memory import PatternMemory, PatternFingerprint, PatternStatus

__all__ = [
    'FeedbackLoop',
    'TradeRecord',
    'TradeOutcome',
    'HardNegatives',
    'NoTradeTemplate',
    'PatternMemory', 
    'PatternFingerprint',
    'PatternStatus'
]