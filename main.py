
from fastapi import FastAPI
from threading import Thread
import time
import os

# --- Simulation Control Flags ---
bot_state = {
    "running": False,
    "trade_log": [],
    "explanations": []
}

app = FastAPI()
from fastapi.middleware.cors import CORSMiddleware

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allow all for now; restrict later for security
    allow_credentials=True,
    allow_headers=["*"],
)

# Import simulation runner
from main_simulation_runner import run_full_simulation as _run_simulation

def simulation_wrapper():
    global bot_state
    bot_state["running"] = True
    bot_state["trade_log"].clear()
    bot_state["explanations"].clear()
    def log_patch(order):
        bot_state["trade_log"].append(order)
        if "reason" in order:
            bot_state["explanations"].append({ "time": order.get("timestamp"), "reason": order["reason"] })
    _run_simulation(log_hook=log_patch)
    bot_state["running"] = False

@app.get("/start")
def start_simulation():
    if bot_state["running"]:
        return { "status": "already running" }
    thread = Thread(target=simulation_wrapper)
    thread.start()
    return { "status": "started" }

@app.get("/stop")
def stop_simulation():
    bot_state["running"] = False
    return { "status": "stopping (will exit after current loop)" }

@app.get("/status")
def get_status():
    return { "running": bot_state["running"], "trades": len(bot_state["trade_log"]) }

@app.get("/log")
def get_log():
    return bot_state["trade_log"][-50:]

@app.get("/explain")
def get_explanations():
    return bot_state["explanations"][-50:]


# main entry for backend


import sys
if "--simulate" in sys.argv:
    from main_simulation_runner import run_full_simulation
    run_full_simulation()
    sys.exit()
# --- End Simulation Hook ---

is_running = False
pnl_total = 0.0
trade_log = []
