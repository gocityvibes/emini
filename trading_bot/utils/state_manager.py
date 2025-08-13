# trading_bot/utils/state_manager.py
from __future__ import annotations

import asyncio
from typing import Optional, List
from datetime import datetime
from pydantic import BaseModel, Field

class SystemState(BaseModel):
    """System state model with AI configuration"""
    
    # Core system state
    running: bool = False
    last_sim_job_id: Optional[str] = None
    last_error: Optional[str] = None
    active_ab_variant: Optional[str] = None
    
    # AI Configuration State
    contract_qty: int = 1
    allowed_directions: List[str] = Field(default_factory=lambda: ["long", "short"]
    )
    prompt_profile_id: str = "default"
    
    # Hybrid Mode State (optional)
    hybrid_enabled: bool = False
    hybrid_score_threshold: float = 80.0
    
    # Metadata
    last_updated: datetime = Field(default_factory=datetime.utcnow)

class StateManager:
    """Thread-safe state manager for the trading bot"""
    
    def __init__(self):
        self._state = SystemState()
        self._lock = asyncio.Lock()
    
    async def get(self) -> SystemState:
        """Get current system state"""
        async with self._lock:
            # Support both Pydantic v1 and v2 copy methods
            if hasattr(self._state, "model_copy"):
                return self._state.model_copy()
            return self._state.copy(deep=True)
    
    async def set(self, **kwargs) -> None:
        """Update system state"""
        async with self._lock:
            for key, value in kwargs.items():
                if hasattr(self._state, key):
                    setattr(self._state, key, value)
            self._state.last_updated = datetime.utcnow()
    
    async def update_ai_config(
        self,
        contract_qty: Optional[int] = None,
        allowed_directions: Optional[List[str]] = None,
        prompt_profile_id: Optional[str] = None,
        hybrid_enabled: Optional[bool] = None,
        hybrid_score_threshold: Optional[float] = None
    ) -> None:
        """Update AI-specific configuration"""
        updates = {}
        
        if contract_qty is not None:
            updates["contract_qty"] = max(1, contract_qty)
        
        if allowed_directions is not None:
            # Validate directions
            valid_directions = [d for d in allowed_directions if d.lower() in ["long", "short"]]
            if valid_directions:
                updates["allowed_directions"] = valid_directions
        
        if prompt_profile_id is not None:
            updates["prompt_profile_id"] = prompt_profile_id
        
        if hybrid_enabled is not None:
            updates["hybrid_enabled"] = hybrid_enabled
        
        if hybrid_score_threshold is not None:
            updates["hybrid_score_threshold"] = max(0.0, min(100.0, hybrid_score_threshold))
        
        if updates:
            await self.set(**updates)
    
    async def get_ai_config(self) -> dict:
        """Get AI configuration as dictionary"""
        state = await self.get()
        return {
            "contract_qty": state.contract_qty,
            "allowed_directions": state.allowed_directions,
            "prompt_profile_id": state.prompt_profile_id,
            "hybrid_enabled": state.hybrid_enabled,
            "hybrid_score_threshold": state.hybrid_score_threshold
        }
    
    async def reset(self) -> None:
        """Reset state to defaults"""
        async with self._lock:
            self._state = SystemState()

# Global state manager instance
state = StateManager()
