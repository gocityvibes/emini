from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import json
from pathlib import Path
import random
from datetime import datetime

app = FastAPI()

# CORS for frontend access
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

trade_log_path = Path("trade_log.json")
pnl_log_path = Path("pnl_log.json")

# Simulate 5 trades
def simulate_trades():
    trades = []
    pnl = []
    for i in range(5):
        direction = random.choice(["long", "short"])
        symbol = random.choice(["ES", "NS"])
        result = random.choice(["win", "loss"])
        entry = round(random.uniform(4500, 4700), 2)
        exit = entry + round(random.uniform(-15, 20), 2) if direction == "long" else entry - round(random.uniform(-15, 20), 2)

        trade = {
            "id": i+1,
            "symbol": symbol,
            "direction": direction,
            "entry": entry,
            "exit": exit,
            "timestamp": datetime.now().isoformat()
        }
        trades.append(trade)

        pnl.append({
            "id": i+1,
            "symbol": symbol,
            "result": result,
            "timestamp": datetime.now().isoformat()
        })

    trade_log_path.write_text(json.dumps(trades, indent=2))
    pnl_log_path.write_text(json.dumps(pnl, indent=2))

simulate_trades()

@app.get("/")
def read_root():
    return {"message": "Emini trade backend with logging active"}

@app.get("/getTradeLog")
def get_trade_log():
    if trade_log_path.exists():
        return json.loads(trade_log_path.read_text())
    return []

@app.get("/getPnL")
def get_pnl_log():
    if pnl_log_path.exists():
        return json.loads(pnl_log_path.read_text())
    return []

@app.get("/getStats")
def get_stats():
    if not pnl_log_path.exists():
        return {"totalTrades": 0, "wins": 0, "losses": 0, "winRate": 0}
    pnl = json.loads(pnl_log_path.read_text())
    wins = len([p for p in pnl if p["result"] == "win"])
    total = len(pnl)
    winrate = round((wins / total) * 100, 2) if total > 0 else 0
    return {
        "totalTrades": total,
        "wins": wins,
        "losses": total - wins,
        "winRate": winrate
    }
