"""
MES Scalper Trading System
Main application package initialization.
"""

__version__ = "1.0.0"
__author__ = "MES Scalper Team"
__description__ = "Automated MES futures scalping system with GPT integration"

# Package-level imports for convenience
from .main import app, create_app

__all__ = ['app', 'create_app']