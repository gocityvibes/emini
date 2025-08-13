from fastapi import WebSocket, APIRouter
from typing import List, Dict, Any
import json
import asyncio
from datetime import datetime

class WebSocketManager:
    """Manages WebSocket connections for real-time updates"""

    def __init__(self):
        self.active_connections: List[WebSocket] = []
        self.last_status = {}

    async def connect(self, websocket: WebSocket):
        """Accept new WebSocket connection"""
        await websocket.accept()
        self.active_connections.append(websocket)
        print(f"WebSocket connected. Total connections: {len(self.active_connections)}")

    async def disconnect(self, websocket: WebSocket):
        """Remove WebSocket connection"""
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)
        print(f"WebSocket disconnected. Total connections: {len(self.active_connections)}")

    async def send_personal_message(self, message: str, websocket: WebSocket):
        """Send message to specific WebSocket"""
        try:
            await websocket.send_text(message)
        except Exception as e:
            print(f"Error sending personal message: {e}")
            await self.disconnect(websocket)

    async def broadcast(self, message: str):
        """Broadcast message to all connected WebSockets"""
        disconnected = []

        for connection in self.active_connections:
            try:
                await connection.send_text(message)
            except Exception as e:
                print(f"Error broadcasting to connection: {e}")
                disconnected.append(connection)

        # Remove disconnected connections
        for connection in disconnected:
            await self.disconnect(connection)

    async def broadcast_json(self, data: Dict[str, Any]):
        """Broadcast JSON data to all connections"""
        message = json.dumps(data, default=str)
        await self.broadcast(message)

    async def send_status_update(self, status_data: Dict[str, Any]):
        """Send status update if data has changed"""

        # Check if status has changed significantly
        if self._has_significant_change(status_data):
            await self.broadcast_json({
                "type": "status_update",
                "data": status_data,
                "timestamp": datetime.utcnow().isoformat()
            })
            self.last_status = status_data.copy()

    async def send_trade_update(self, trade_data: Dict[str, Any]):
        """Send new trade notification"""
        await self.broadcast_json({
            "type": "new_trade",
            "data": trade_data,
            "timestamp": datetime.utcnow().isoformat()
        })

    async def send_simulation_progress(self, progress_data: Dict[str, Any]):
        """Send simulation progress update"""
        await self.broadcast_json({
            "type": "simulation_progress",
            "data": progress_data,
            "timestamp": datetime.utcnow().isoformat()
        })

    async def send_error_notification(self, error_message: str, context: Dict[str, Any] = None):
        """Send error notification"""
        await self.broadcast_json({
            "type": "error",
            "data": {
                "message": error_message,
                "context": context or {},
                "timestamp": datetime.utcnow().isoformat()
            }
        })

    async def send_batch_completion(self, batch_data: Dict[str, Any]):
        """Send batch completion notification"""
        await self.broadcast_json({
            "type": "batch_completed",
            "data": batch_data,
            "timestamp": datetime.utcnow().isoformat()
        })

    async def send_ai_analysis_update(self, analysis_data: Dict[str, Any]):
        """Send AI analysis update"""
        await self.broadcast_json({
            "type": "ai_analysis",
            "data": analysis_data,
            "timestamp": datetime.utcnow().isoformat()
        })

    async def send_learning_update(self, learning_data: Dict[str, Any]):
        """Send learning system update notification"""
        await self.broadcast_json({
            "type": "learning_update",
            "data": learning_data,
            "timestamp": datetime.utcnow().isoformat()
        })

    async def send_ab_test_update(self, ab_data: Dict[str, Any]):
        """Send A/B test results update"""
        await self.broadcast_json({
            "type": "ab_test_update",
            "data": ab_data,
            "timestamp": datetime.utcnow().isoformat()
        })

    async def send_simulation_started(self, simulation_data: Dict[str, Any]):
        """Send simulation started notification"""
        await self.broadcast_json({
            "type": "simulation_started",
            "data": simulation_data,
            "timestamp": datetime.utcnow().isoformat()
        })

    async def send_simulation_completed(self, simulation_data: Dict[str, Any]):
        """Send simulation completed notification"""
        await self.broadcast_json({
            "type": "simulation_completed",
            "data": simulation_data,
            "timestamp": datetime.utcnow().isoformat()
        })

    def _has_significant_change(self, new_status: Dict[str, Any]) -> bool:
        """Check if status has changed significantly enough to broadcast"""

        if not self.last_status:
            return True

        # Check simulation progress
        old_progress = self.last_status.get("simulation_progress", {})
        new_progress = new_status.get("simulation_progress", {})

        if old_progress.get("current", 0) != new_progress.get("current", 0):
            return True

        # Check running status
        if self.last_status.get("is_running") != new_status.get("is_running"):
            return True

        # Check current analysis changes
        old_analysis = self.last_status.get("current_analysis", {})
        new_analysis = new_status.get("current_analysis", {})

        if old_analysis.get("symbol") != new_analysis.get("symbol"):
            return True
        if old_analysis.get("status") != new_analysis.get("status"):
            return True

        # Check daily performance changes
        old_daily = self.last_status.get("daily_performance", {})
        new_daily = new_status.get("daily_performance", {})

        if old_daily.get("total_trades", 0) != new_daily.get("total_trades", 0):
            return True
        if abs(old_daily.get("win_rate", 0) - new_daily.get("win_rate", 0)) > 1.0:  # >1% change
            return True

        # Check AI configuration changes
        old_ai = self.last_status.get("ai_config", {})
        new_ai = new_status.get("ai_config", {})

        if old_ai.get("contract_qty") != new_ai.get("contract_qty"):
            return True
        if old_ai.get("prompt_profile_id") != new_ai.get("prompt_profile_id"):
            return True

        return False

    def get_connection_count(self) -> int:
        """Get number of active connections"""
        return len(self.active_connections)

    async def ping_all_connections(self):
        """Send ping to all connections to keep them alive"""
        await self.broadcast_json({
            "type": "ping",
            "data": {"timestamp": datetime.utcnow().isoformat()}
        })

    async def send_heartbeat(self):
        """Send periodic heartbeat to maintain connections"""
        while True:
            if self.active_connections:
                await self.ping_all_connections()
            await asyncio.sleep(30)  # Heartbeat every 30 seconds

# Global WebSocket manager instance
websocket_manager = WebSocketManager()

# WebSocket event handlers for integration with other services

async def notify_trade_executed(trade_data: Dict[str, Any]):
    """Notify all clients when a trade is executed"""
    await websocket_manager.send_trade_update(trade_data)

async def notify_simulation_started(simulation_data: Dict[str, Any]):
    """Notify all clients when a simulation starts"""
    await websocket_manager.send_simulation_started(simulation_data)

async def notify_simulation_completed(simulation_data: Dict[str, Any]):
    """Notify all clients when a simulation completes"""
    await websocket_manager.send_simulation_completed(simulation_data)

async def notify_batch_started(batch_data: Dict[str, Any]):
    """Notify all clients when a batch starts"""
    await websocket_manager.broadcast_json({
        "type": "batch_started",
        "data": batch_data
    })

async def notify_batch_completed(batch_data: Dict[str, Any]):
    """Notify all clients when a batch completes"""
    await websocket_manager.send_batch_completion(batch_data)

async def notify_ai_decision(decision_data: Dict[str, Any]):
    """Notify all clients of AI decisions"""
    await websocket_manager.send_ai_analysis_update(decision_data)

async def notify_learning_update(learning_data: Dict[str, Any]):
    """Notify all clients of learning system updates"""
    await websocket_manager.send_learning_update(learning_data)

async def notify_ab_test_update(ab_data: Dict[str, Any]):
    """Notify all clients of A/B test updates"""
    await websocket_manager.send_ab_test_update(ab_data)

async def notify_error(error_message: str, context: Dict[str, Any] = None):
    """Notify all clients of errors"""
    await websocket_manager.send_error_notification(error_message, context)

async def notify_status_change(status_data: Dict[str, Any]):
    """Notify all clients of status changes"""
    await websocket_manager.send_status_update(status_data)

# Export router for FastAPI integration
router = APIRouter()

# Add any WebSocket-specific routes if needed
@router.get("/connections")
async def get_connection_count():
    """Get current WebSocket connection count"""
    return {
        "active_connections": websocket_manager.get_connection_count(),
        "timestamp": datetime.utcnow().isoformat()
    }
