import trading_bot.datetime_fix  # Auto-applies DateTime -> ISO patch

# trading_bot/app.py - Complete FastAPI Application with GPT-5 Integration

from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.websockets import WebSocket, WebSocketDisconnect
import asyncio
import json
from typing import Dict, Any
from datetime import datetime
from contextlib import asynccontextmanager

from .config import API_HOST, API_PORT, CORS_ORIGINS
from .services.database import db
from .services.simulation_engine import run_simulation_batch
from .utils.state_manager import state
from .api.dashboard import dashboard_router
from .api.ab_testing import router as ab_router
from .api.simulation import simulation_router
from .api.websocket import websocket_manager
from .api.admin import admin_router

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan management"""
    # Startup
    print("Starting GPT-5 Trading Bot API...")

    # Connect to database
    try:
        await db.start()
        print("Database connected successfully")
    except Exception as e:
        print(f"Failed to connect to database: {e}")
        raise

    # Initialize learning system
    try:
        from .services.learning_system import apply_learning_update
        await apply_learning_update({"startup": True})
        print("Learning system initialized successfully")
    except Exception as e:
        print(f"Failed to initialize learning system: {e}")
        # Don't fail startup if learning system fails

    # Start WebSocket heartbeat
    try:
        asyncio.create_task(websocket_manager.send_heartbeat())
        print("WebSocket heartbeat started")
    except Exception as e:
        print(f"Failed to start WebSocket heartbeat: {e}")

    yield

    # Shutdown
    print("Shutting down GPT-5 Trading Bot API...")

    # Stop database
    await db.stop()
    print("Database disconnected")


# Create FastAPI app
app = FastAPI(
    title="GPT-5 AI Trading Bot",
    description="GPT-5 powered trading simulation and learning system with hybrid mode support",
    version="1.0.0",
    lifespan=lifespan
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include API routers
app.include_router(dashboard_router, prefix="/dashboard", tags=["dashboard"])
app.include_router(simulation_router, prefix="/simulate", tags=["simulation"])
app.include_router(admin_router, prefix="/admin", tags=["admin"])
app.include_router(ab_router, prefix="/ab", tags=["ab-testing"])

@app.get("/")
async def root():
    return {
        "message": "GPT-5 AI Trading Bot API",
        "version": "1.0.0",
        "status": "running",
        "features": [
            "GPT-5 Decision Engine",
            "Hybrid Mode with GPT-4.1 Prefiltering", 
            "Continuous Learning System",
            "A/B Testing Framework",
            "Real-time WebSocket Updates",
            "200+ Trades/Day Simulation Capacity"
        ]
    }

@app.get("/healthz")
async def healthz():
    return {"ok": True}

@app.get("/api/health")
async def health_check():
    try:
        current_state = await state.get()
        return {
            "status": "healthy",
            "timestamp": datetime.utcnow().isoformat(),
            "last_error": current_state.last_error,
            "database": {
                "type": "memory" if db.use_memory else "mongodb",
                "status": "connected"
            },
            "simulation_engine": {
                "is_running": current_state.running,
                "last_job": current_state.last_sim_job_id
            },
            "state_manager": {
                "is_running": current_state.running,
                "ab_variant": current_state.active_ab_variant
            },
            "ai_config": {
                "contract_qty": current_state.contract_qty,
                "allowed_directions": current_state.allowed_directions,
                "prompt_profile_id": current_state.prompt_profile_id,
                "hybrid_enabled": current_state.hybrid_enabled,
                "hybrid_threshold": current_state.hybrid_score_threshold
            },
            "websocket": {
                "active_connections": websocket_manager.get_connection_count()
            }
        }
    except Exception as e:
        return {
            "status": "unhealthy",
            "error": str(e),
            "timestamp": datetime.utcnow().isoformat()
        }

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket_manager.connect(websocket)
    try:
        current_state = await state.get()
        await websocket.send_text(json.dumps({
            "type": "initial_status",
            "data": {
                "running": current_state.running,
                "last_job": current_state.last_sim_job_id,
                "ab_variant": current_state.active_ab_variant,
                "ai_config": {
                    "contract_qty": current_state.contract_qty,
                    "allowed_directions": current_state.allowed_directions,
                    "prompt_profile_id": current_state.prompt_profile_id,
                    "hybrid_enabled": current_state.hybrid_enabled
                }
            }
        }))

        while True:
            await asyncio.sleep(5)
            current_state = await state.get()
            await websocket.send_text(json.dumps({
                "type": "status_update",
                "data": {
                    "running": current_state.running,
                    "last_job": current_state.last_sim_job_id,
                    "ab_variant": current_state.active_ab_variant,
                    "timestamp": datetime.utcnow().isoformat(),
                    "ai_config": {
                        "contract_qty": current_state.contract_qty,
                        "prompt_profile_id": current_state.prompt_profile_id,
                        "hybrid_enabled": current_state.hybrid_enabled
                    }
                }
            }))

    except WebSocketDisconnect:
        print("WebSocket client disconnected")
    except Exception as e:
        print(f"WebSocket error: {e}")
    finally:
        await websocket_manager.disconnect(websocket)

@app.post("/api/test/simulation")
async def run_test_simulation(background_tasks: BackgroundTasks):
    current_state = await state.get()
    if current_state.running:
        raise HTTPException(status_code=400, detail="Simulation engine is busy")

    async def run_test():
        try:
            await state.set(running=True)
            ai_config = await state.get_ai_config()
            test_config = {
                "symbol": "MES", 
                "total_simulations": 5,
                "contract_qty": ai_config["contract_qty"],
                "allowed_directions": ai_config["allowed_directions"],
                "prompt_profile_id": ai_config["prompt_profile_id"],
                "hybrid_enabled": ai_config["hybrid_enabled"]
            }
            result = await run_simulation_batch(test_config)
            await state.set(running=False, last_sim_job_id=result["job_id"])
            await websocket_manager.send_simulation_completed({
                "job_id": result["job_id"],
                "total_trades": result["total_trades"],
                "ai_performance": result.get("batch_metrics", {}),
                "message": "Test simulation completed successfully"
            })
            return result
        except Exception as e:
            await state.set(running=False, last_error=str(e))
            await websocket_manager.send_error_notification(f"Test simulation failed: {str(e)}")
            raise

    background_tasks.add_task(run_test)
    return {
        "message": "GPT-5 test simulation started",
        "status": "running",
        "ai_config": await state.get_ai_config(),
        "estimated_duration": "30-60 seconds",
        "timestamp": datetime.utcnow().isoformat()
    }

@app.get("/api/system/info")
async def get_system_info():
    current_state = await state.get()
    return {
        "system": {
            "name": "GPT-5 AI Trading Bot",
            "version": "1.0.0",
            "environment": "development" if db.use_memory else "production",
            "uptime": "active"
        },
        "ai_engine": {
            "primary_model": "gpt-5",
            "hybrid_model": "ft:gpt-4.1-mini",
            "active_profile": current_state.prompt_profile_id,
            "hybrid_enabled": current_state.hybrid_enabled,
            "learning_enabled": True
        },
        "trading": {
            "primary_symbol": "MES",
            "contract_qty": current_state.contract_qty,
            "allowed_directions": current_state.allowed_directions,
            "scalping_strategy": "1pt target, 1.25pt stop"
        },
        "capabilities": {
            "max_simulations_per_day": "200+",
            "real_time_learning": True,
            "a_b_testing": True,
            "websocket_updates": True,
            "hybrid_cost_optimization": current_state.hybrid_enabled
        },
        "status": {
            "simulation_running": current_state.running,
            "websocket_connections": websocket_manager.get_connection_count(),
            "last_error": current_state.last_error,
            "database_type": "memory" if db.use_memory else "mongodb"
        },
        "timestamp": datetime.utcnow().isoformat()
    }

if __name__ == "__main__":
    import uvicorn
    print(f"Starting GPT-5 Trading Bot server on {API_HOST}:{API_PORT}")
    uvicorn.run("trading_bot.app:app",
        host=API_HOST,
        port=API_PORT,
        reload=True,
        log_level="info"
    )
