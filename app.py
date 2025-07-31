
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from threading import Thread
import time
import uvicorn

from mock_broker import MockTradeStationBroker
from simulate_engine import generate_simulated_candles
from sim_broker_interface import sim_place_ts_order, sim_get_open_position, sim_apply_trailing_stop
from indicator_engine import compute_indicators
from phase_3_scoring_gpt4o import score_trade_with_gpt4o
from phase_4_filters import chrome_filter, shadow_filter, iron_curtain_filter

from datetime import datetime, timedelta
import pytz
import pandas as pd

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

sim_running = False
log = []
mock_broker = MockTradeStationBroker()
global_df = pd.DataFrame()
symbols = ["MNQ=F", "MES=F"]
sim_time = datetime.now(pytz.timezone('US/Eastern'))

def run_simulation():
    global sim_running, global_df, sim_time

    while sim_running:
        try:
            for symbol in symbols:
                new_df = generate_simulated_candles(
                    symbol=symbol,
                    start_datetime=sim_time,
                    num_candles=1,
                    interval_minutes=1,
                    start_price=global_df['Close'].iloc[-1] if not global_df.empty else 19000.0,
                    volatility=0.0001,
                    drift=0.000005,
                    trend_strength=0.00001,
                    chop_strength=0.00005
                )
                sim_time += timedelta(minutes=1)
                global_df = pd.concat([global_df, new_df])
                mock_broker.set_sim_time(sim_time.strftime('%Y-%m-%d %H:%M'))
                mock_broker.update_quote(symbol, new_df['Close'].iloc[-1])
                if len(global_df) < 21:
                    continue
                df = compute_indicators(global_df.copy())
                row = df.iloc[-1]
                if row.isnull().any():
                    continue
                indicators = {
                    "price": row['Close'],
                    "RSI": row['RSI'],
                    "MACD_Hist": row['MACD_Hist'],
                    "EMA_8": row['EMA_8'],
                    "EMA_21": row['EMA_21'],
                    "VWAP": row['VWAP'],
                    "ATR": row['ATR'],
                    "time": sim_time.strftime('%H:%M')
                }
                if not chrome_filter(df, indicators): continue
                if not shadow_filter(df, indicators): continue
                if not iron_curtain_filter(indicators["time"], news_flags={}): continue
                gpt_result = score_trade_with_gpt4o(indicators)
                direction = gpt_result.get("direction", "none")
                score = gpt_result.get("score", 0)
                if score < 95:
                    continue
                log.append({
                    "time": sim_time.strftime('%Y-%m-%d %H:%M'),
                    "symbol": symbol,
                    "action": direction.upper(),
                    "score": score,
                    "price": row['Close']
                })
                pos = sim_get_open_position(mock_broker, symbol)
                if pos:
                    sim_apply_trailing_stop(mock_broker, symbol, pos['entry_price'], 5.0, pos['side'], pos['qty'], 60)
                elif direction in ["long", "short"]:
                    side = "buy" if direction == "long" else "sell"
                    atr = indicators["ATR"]
                    stop = row['Close'] - (atr * 2) if side == "buy" else row['Close'] + (atr * 2)
                    limit = row['Close'] + (atr * 4) if side == "buy" else row['Close'] - (atr * 4)
                    sim_place_ts_order(mock_broker, symbol, side, 1, stop, limit)

        except Exception as e:
            log.append({"error": str(e)})

        time.sleep(1)

@app.post("/start")
def start_sim():
    global sim_running
    if not sim_running:
        sim_running = True
        thread = Thread(target=run_simulation, daemon=True)
        thread.start()
    return {"status": "started"}

@app.post("/stop")
def stop_sim():
    global sim_running
    sim_running = False
    return {"status": "stopped"}

@app.get("/log")
def get_log():
    return {"log": log[-100:]}  # return last 100 entries
