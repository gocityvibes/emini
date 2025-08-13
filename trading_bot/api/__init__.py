"""API routers and endpoints

This module contains all the FastAPI routers:
- Dashboard API (performance metrics, status)
- Simulation API (start/stop simulations, configuration)
- Admin API (learning system management)
- WebSocket management (real-time updates)
- A/B Testing API (preset comparison and optimization)
"""

from .dashboard import dashboard_router
from .simulation import simulation_router
from .admin import admin_router
from .websocket import websocket_manager, router as websocket_router
from .ab_testing import router as ab_router

__all__ = [
    "dashboard_router",
    "simulation_router", 
    "admin_router",
    "websocket_manager",
    "websocket_router",
    "ab_router"
]
