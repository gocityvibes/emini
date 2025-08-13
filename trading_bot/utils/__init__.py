# trading_bot/utils/__init__.py
"""
Utility modules for the AI trading bot.

This module contains:
- State manager (system state and configuration)
- Pydantic shim (model compatibility utilities)
"""

from .state_manager import state, StateManager, SystemState
from .pydantic_shim import model_to_dict, dict_to_model, model_json_schema, safe_model_dump

__all__ = [
    # State Management
    "state",
    "StateManager", 
    "SystemState",
    
    # Pydantic Utilities
    "model_to_dict",
    "dict_to_model",
    "model_json_schema",
    "safe_model_dump"
]
