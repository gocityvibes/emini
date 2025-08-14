"""WebSocket Manager for MES Scalping Strategy

Manages real-time WebSocket connections and broadcasts for the MES scalping system,
including settings updates, scalp KPIs, trade events, and system notices.
"""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import WebSocket
from trading_bot.serializers import dumps


class WebSocketManager:
    """Manages WebSocket connections for real-time updates."""

    def __init__(self) -> None:
        self.active_connections: List[WebSocket] = []
        self.last_status: Dict[str, Any] = {}

    async def connect(self, websocket: WebSocket) -> None:
        """Accept a new WebSocket connection."""
        await websocket.accept()
        self.active_connections.append(websocket)
        print(f"WebSocket connected. Total connections: {len(self.active_connections)}")

    async def disconnect(self, websocket: WebSocket) -> None:
        """Remove a WebSocket connection."""
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)
        print(f"WebSocket disconnected. Total connections: {len(self.active_connections)}")

    async def send_personal_message(self, message: str, websocket: WebSocket) -> None:
        """Send a message to a specific WebSocket."""
        try:
            await websocket.send_text(message)
        except Exception as e:  # pragma: no cover
            print(f"Error sending personal message: {e}")
            await self.disconnect(websocket)

    async def broadcast(self, message: str) -> None:
        """Broadcast a text message to all connected WebSockets."""
        disconnected: List[WebSocket] = []
        for connection in list(self.active_connections):
            try:
                await connection.send_text(message)
            except Exception as e:  # pragma: no cover
                print(f"Error broadcasting to connection: {e}")
                disconnected.append(connection)

        for connection in disconnected:
            await self.disconnect(connection)

    async def broadcast_json(self, data: Dict[str, Any]) -> None:
        """Broadcast JSON-serializable data to all connections."""
        message = dumps(data)
        await self.broadcast(message)

    async def send_status_update(self, status_data: Dict[str, Any]) -> None:
        """Send a status update if the data has changed meaningfully."""
        if self._has_significant_change(status_data):
            await self.broadcast_json({
                "type": "status_update",
                "data": self._ensure_json_safe(status_data),
                "timestamp": datetime.utcnow().isoformat(),
            })
            self.last_status = dict(status_data)

    async def send_trade_update(self, trade_data: Dict[str, Any]) -> None:
        """Send a new trade notification."""
        await self.broadcast_json({
            "type": "new_trade",
            "data": self._ensure_json_safe(trade_data),
            "timestamp": datetime.utcnow().isoformat(),
        })

    async def send_simulation_progress(self, progress_data: Dict[str, Any]) -> None:
        """Send a simulation progress update."""
        await self.broadcast_json({
            "type": "simulation_progress",
            "data": self._ensure_json_safe(progress_data),
            "timestamp": datetime.utcnow().isoformat(),
        })

    async def send_error_notification(self, error_message: str, context: Optional[Dict[str, Any]] = None) -> None:
        """Send an error notification."""
        await self.broadcast_json({
            "type": "error",
            "data": {
                "message": str(error_message),
                "context": self._ensure_json_safe(context or {}),
                "timestamp": datetime.utcnow().isoformat(),
            },
        })

    async def send_batch_completion(self, batch_data: Dict[str, Any]) -> None:
        """Send a batch completion notification."""
        await self.broadcast_json({
            "type": "batch_completed",
            "data": self._ensure_json_safe(batch_data),
            "timestamp": datetime.utcnow().isoformat(),
        })

    async def send_ai_analysis_update(self, analysis_data: Dict[str, Any]) -> None:
        """Send an AI analysis update."""
        await self.broadcast_json({
            "type": "ai_analysis",
            "data": self._ensure_json_safe(analysis_data),
            "timestamp": datetime.utcnow().isoformat(),
        })

    # MES Scalping broadcast helpers
    async def broadcast_settings_snapshot(self, snapshot: Dict[str, Any]) -> None:
        """Broadcast the current settings snapshot for MES scalping strategy."""
        await self.broadcast_json({
            "type": "settings_snapshot",
            "data": {"settings": self._ensure_json_safe(snapshot), "updated_at": datetime.utcnow().isoformat()},
            "timestamp": datetime.utcnow().isoformat(),
        })

    async def broadcast_scalp_kpis(self, payload: Dict[str, Any]) -> None:
        """Broadcast scalp-specific KPIs (hit rate, time-to-target, MAE/MFE)."""
        await self.broadcast_json({
            "type": "scalp_kpis",
            "data": {"kpis": self._ensure_json_safe(payload), "updated_at": datetime.utcnow().isoformat()},
            "timestamp": datetime.utcnow().isoformat(),
        })

    async def broadcast_trade_event(self, trade_dict: Dict[str, Any]) -> None:
        """Broadcast a trade execution event with scalping details."""
        await self.broadcast_json({
            "type": "trade_event",
            "data": {"trade": self._ensure_json_safe(trade_dict), "event_time": datetime.utcnow().isoformat()},
            "timestamp": datetime.utcnow().isoformat(),
        })

    async def broadcast_system_notice(self, message: str) -> None:
        """Broadcast a system notice or alert message."""
        await self.broadcast_json({
            "type": "system_notice",
            "data": {"message": str(message), "notice_time": datetime.utcnow().isoformat()},
            "timestamp": datetime.utcnow().isoformat(),
        })

    def _ensure_json_safe(self, data: Any) -> Any:
        """Ensure data is JSON-safe by converting problematic types."""
        if isinstance(data, dict):
            return {k: self._ensure_json_safe(v) for k, v in data.items()}
        if isinstance(data, list):
            return [self._ensure_json_safe(v) for v in data]
        if isinstance(data, datetime):
            return data.isoformat()
        if hasattr(data, "dict") and callable(getattr(data, "dict")):  # Pydantic models
            try:
                return self._ensure_json_safe(data.dict())
            except Exception:
                return str(data)
        if hasattr(data, "__dict__") and not isinstance(data, (str, int, float, bool)):
            return str(data)
        return data

    def _has_significant_change(self, new_status: Dict[str, Any]) -> bool:
        """Check if status has changed enough to warrant a broadcast."""
        if not self.last_status:
            return True

        # Simulation progress
        old_prog = self.last_status.get("simulation_progress", {}) or {}
        new_prog = new_status.get("simulation_progress", {}) or {}
        if (old_prog.get("current") or 0) != (new_prog.get("current") or 0):
            return True

        # Running status
        if self.last_status.get("is_running") != new_status.get("is_running"):
            return True

        # Current analysis changes
        old_ana = self.last_status.get("current_analysis", {}) or {}
        new_ana = new_status.get("current_analysis", {}) or {}
        if old_ana.get("symbol") != new_ana.get("symbol"):
            return True
        if old_ana.get("status") != new_ana.get("status"):
            return True

        # Daily performance changes (treat win_rate as fraction 0..1)
        old_daily = self.last_status.get("daily_performance", {}) or {}
        new_daily = new_status.get("daily_performance", {}) or {}
        if (old_daily.get("total_trades") or 0) != (new_daily.get("total_trades") or 0):
            return True
        if abs((old_daily.get("win_rate") or 0.0) - (new_daily.get("win_rate") or 0.0)) > 0.01:  # >1% change
            return True

        # Scalp metrics changes (hit_rate fraction 0..1)
        old_scalp = self.last_status.get("scalp_metrics", {}) or {}
        new_scalp = new_status.get("scalp_metrics", {}) or {}
        if abs((old_scalp.get("hit_rate") or 0.0) - (new_scalp.get("hit_rate") or 0.0)) > 0.02:  # >2% change
            return True

        # Time-to-target: support both keys
        old_ttt = (old_scalp.get("avg_time_to_target_sec") or old_scalp.get("avg_time_to_target") or 0.0)
        new_ttt = (new_scalp.get("avg_time_to_target_sec") or new_scalp.get("avg_time_to_target") or 0.0)
        try:
            if abs(float(old_ttt) - float(new_ttt)) > 5.0:  # >5s change
                return True
        except Exception:
            pass

        return False

    def get_connection_count(self) -> int:
        """Return the number of active connections."""
        return len(self.active_connections)

    async def ping_all_connections(self) -> None:
        """Send a ping to all connections to keep them alive."""
        await self.broadcast_json({"type": "ping", "data": {"timestamp": datetime.utcnow().isoformat()}})


# Global WebSocket manager instance
websocket_manager = WebSocketManager()


# Convenience event helpers

async def notify_trade_executed(trade_data: Dict[str, Any]) -> None:
    """Notify all clients when a trade is executed."""
    await websocket_manager.send_trade_update(trade_data)

async def notify_simulation_started(simulation_data: Dict[str, Any]) -> None:
    """Notify all clients when a simulation starts."""
    await websocket_manager.broadcast_json({"type": "simulation_started", "data": websocket_manager._ensure_json_safe(simulation_data)})

async def notify_simulation_completed(simulation_data: Dict[str, Any]) -> None:
    """Notify all clients when a simulation completes."""
    await websocket_manager.broadcast_json({"type": "simulation_completed", "data": websocket_manager._ensure_json_safe(simulation_data)})

async def notify_batch_started(batch_data: Dict[str, Any]) -> None:
    """Notify all clients when a batch starts."""
    await websocket_manager.broadcast_json({"type": "batch_started", "data": websocket_manager._ensure_json_safe(batch_data)})

async def notify_batch_completed(batch_data: Dict[str, Any]) -> None:
    """Notify all clients when a batch completes."""
    await websocket_manager.send_batch_completion(batch_data)

async def notify_ai_decision(decision_data: Dict[str, Any]) -> None:
    """Notify all clients of AI decisions."""
    await websocket_manager.send_ai_analysis_update(decision_data)

async def notify_error(error_message: str, context: Optional[Dict[str, Any]] = None) -> None:
    """Notify all clients of errors."""
    await websocket_manager.send_error_notification(error_message, context)

async def notify_status_change(status_data: Dict[str, Any]) -> None:
    """Notify all clients of status changes."""
    await websocket_manager.send_status_update(status_data)

async def notify_settings_update(settings_snapshot: Dict[str, Any]) -> None:
    """Notify all clients of settings changes."""
    await websocket_manager.broadcast_settings_snapshot(settings_snapshot)

async def notify_scalp_metrics_update(kpis: Dict[str, Any]) -> None:
    """Notify all clients of updated scalping KPIs."""
    await websocket_manager.broadcast_scalp_kpis(kpis)

async def notify_trade_executed_enhanced(trade_dict: Dict[str, Any]) -> None:
    """Enhanced trade notification with scalping details."""
    await websocket_manager.broadcast_trade_event(trade_dict)

async def notify_system_alert(message: str) -> None:
    """Notify all clients of system alerts or notices."""
    await websocket_manager.broadcast_system_notice(message)
