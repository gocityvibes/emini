# live_runner.py - real-time loop and broker state
import threading
import time
import json
from datetime import datetime
from simulate_engine import generate_simulated_candles
from indicator_engine import compute_indicators
from phase_3_scoring_gpt4o import score_trade_with_gpt4o
from phase_4_filters import chrome_filter, shadow_filter, iron_curtain_filter
from mock_broker import MockTradeStationBroker
from sim_broker_interface import sim_place_ts_order, sim_get_open_position, sim_apply_trailing_stop

SIM_SYMBOL = "MES=F"
TRAIL_AMOUNT = 5.0
GPT_SCORE_THRESHOLD = 95

broker = MockTradeStationBroker()
run_flag = threading.Event()
bot_thread = None

def run_loop():
    global broker
    broker = MockTradeStationBroker()
    df = None
    last_close = 4900.0

    while run_flag.is_set():
        candles = generate_simulated_candles(SIM_SYMBOL, datetime.now(), 1, start_price=last_close)
        last_close = candles["Close"].iloc[-1]
        broker.set_sim_time(datetime.now().strftime('%Y-%m-%d %H:%M'))
        broker.update_quote(SIM_SYMBOL, last_close)

        df = df.append(candles) if df is not None else candles
        if len(df) < 21:
            time.sleep(1)
            continue
        df_ind = compute_indicators(df.copy())
        if df_ind.empty or df_ind.iloc[-1].isnull().any():
            time.sleep(1)
            continue

        indicators = {
            "price": df_ind["Close"].iloc[-1],
            "RSI": df_ind["RSI"].iloc[-1],
            "MACD_Hist": df_ind["MACD_Hist"].iloc[-1],
            "EMA_8": df_ind["EMA_8"].iloc[-1],
            "EMA_21": df_ind["EMA_21"].iloc[-1],
            "VWAP": df_ind["VWAP"].iloc[-1],
            "ATR": df_ind["ATR"].iloc[-1],
            "time": datetime.now().strftime("%H:%M")
        }

        if not chrome_filter(df_ind, indicators): time.sleep(1); continue
        if not shadow_filter(df_ind, indicators): time.sleep(1); continue
        if not iron_curtain_filter(indicators["time"], {}): time.sleep(1); continue

        try:
            gpt_result = score_trade_with_gpt4o(indicators)
        except Exception as e:
            print("GPT ERROR:", e)
            time.sleep(1)
            continue

        score = gpt_result.get("score", 0)
        direction = gpt_result.get("direction", "none")
        if score < GPT_SCORE_THRESHOLD:
            time.sleep(1)
            continue

        open_pos = sim_get_open_position(broker, SIM_SYMBOL)
        if open_pos:
            sim_apply_trailing_stop(broker, SIM_SYMBOL, open_pos["entry_price"], TRAIL_AMOUNT,
                                    open_pos["side"], open_pos["qty"], 60)
        elif direction in ["long", "short"]:
            qty = 1
            price = indicators["price"]
            atr = indicators["ATR"]
            side = "buy" if direction == "long" else "sell"
            stop_price = price - 2 * atr if direction == "long" else price + 2 * atr
            limit_price = price + 4 * atr if direction == "long" else price - 4 * atr
            trade = sim_place_ts_order(broker, SIM_SYMBOL, side, qty, stop_price, limit_price)

        # Log trade state
        log_state()

        time.sleep(1)

def log_state():
    summary = get_summary()
    with open("logs/simbot_log.jsonl", "a") as f:
        f.write(json.dumps(summary) + "\n")

def start_bot():
    global bot_thread
    run_flag.set()
    bot_thread = threading.Thread(target=run_loop)
    bot_thread.start()

def stop_bot():
    run_flag.clear()
    if bot_thread:
        bot_thread.join()

def is_running():
    return run_flag.is_set()

def get_summary():
    return {
        "balance": broker.get_balance(),
        "net_pnl": broker.get_net_pnl(),
        "open_positions": broker.get_open_positions("SIM"),
        "order_history": broker.get_order_history()
    }