# trading_bot/services/__init__.py
"""
Core services for the AI trading bot.

This module contains:
- Database service (MongoDB/memory storage)
- AI service (GPT-5 decision making)
- Prefilter service (GPT-4.1 hybrid mode)
- Simulation engine (AI-powered trading simulation)
- Learning system (prompt optimization)
- Outcome logging (decision/result tracking)
- Prompt library (AI prompt management)
"""

from .database import db, DatabaseService
from .ai_service import get_trade_decision, AIDecisionError
from .ai_prefilter_service import score_setup, PrefilterError
from .simulation_engine import simulation_engine, run_simulation_batch
from .learning_system import update_prompt_profile, apply_learning_update, extract_learning_patterns
from .outcome_logger import log_decision, log_outcome, log_prefilter
from .prompt_library import get_profile, save_profile, list_profiles

__all__ = [
    # Database
    "db",
    "DatabaseService",
    
    # AI Services
    "get_trade_decision",
    "AIDecisionError",
    "score_setup", 
    "PrefilterError",
    
    # Simulation
    "simulation_engine",
    "run_simulation_batch",
    
    # Learning
    "update_prompt_profile",
    "apply_learning_update", 
    "extract_learning_patterns",
    
    # Logging
    "log_decision",
    "log_outcome", 
    "log_prefilter",
    
    # Prompt Management
    "get_profile",
    "save_profile",
    "list_profiles"
]
