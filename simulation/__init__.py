"""
Simulation Module
Realistic trade simulation with advanced bracket orders.
"""

from .realistic_sim import RealisticSimulator, TradeResult, ExitReason, TradeDirection

__all__ = [
    'RealisticSimulator',
    'TradeResult', 
    'ExitReason',
    'TradeDirection'
]