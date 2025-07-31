from fastapi import FastAPI
from main_simulation_runner import run_full_simulation
import json

app = FastAPI()

@app.get("/start")
def start_sim():
    run_full_simulation()
    return {"status": "Simulation started"}

@app.get("/log")
def get_log():
    with open("logs/trade_log.json", "r") as f:
        return json.load(f)

@app.get("/explain")
def explain():
    return {
        "note": "Simulation uses EMA + MACD + Chrome + Shadow + Iron Curtain + Sentinel. Trades every 2 minutes, max 50 trades."
    }
