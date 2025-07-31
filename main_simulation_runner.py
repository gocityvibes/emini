from helpers import *
from chrome import chrome_filter
from shadow import shadow_filter
from iron_curtain import iron_curtain_filter
from sentinel import sentinel_says_exit
from ema import calculate_ema
from macd import calculate_macd
import json
import time

def score_trade_with_gpt4o(indicators):
    if indicators['EMA_8'] > indicators['EMA_21'] and indicators['MACD_Hist'] > 0:
        return {
            "pattern": "Bullish EMA + MACD setup",
            "direction": "long",
            "score": 95,
            "reason": "EMA 8 > EMA 21 and MACD bullish"
        }
    elif indicators['EMA_8'] < indicators['EMA_21'] and indicators['MACD_Hist'] < 0:
        return {
            "pattern": "Bearish EMA + MACD setup",
            "direction": "short",
            "score": 93,
            "reason": "EMA 8 < EMA 21 and MACD bearish"
        }
    else:
        return {
            "pattern": "No clear signal",
            "direction": "none",
            "score": 70,
            "reason": "Indicators neutral"
        }

def run_full_simulation(log_hook=print):
    with open("candles.json", "r") as f:
        candles = json.load(f)

    trade_log = []
    active_trade = None
    trade_timer = 0
    trade_count = 0

    for i, candle in enumerate(candles):
        indicators = {
            "EMA_8": calculate_ema(candles[:i+1], 8),
            "EMA_21": calculate_ema(candles[:i+1], 21),
            "MACD_Hist": calculate_macd(candles[:i+1])['hist']
        }

        if active_trade:
            trade_timer += 1
            if trade_timer >= 2:
                active_trade["exit_price"] = candle["close"]
                active_trade["exit_time"] = candle["time"]
                active_trade["pnl"] = round((active_trade["exit_price"] - active_trade["entry_price"]) * (1 if active_trade["direction"] == "long" else -1), 2)
                trade_log.append(active_trade)
                log_hook(f"Exited trade: {active_trade}")
                active_trade = None
                trade_timer = 0
            continue

        score_data = score_trade_with_gpt4o(indicators)

        if score_data['direction'] != 'none' and chrome_filter(indicators) and shadow_filter(indicators) and iron_curtain_filter(indicators):
            active_trade = {
                "entry_price": candle["close"],
                "entry_time": candle["time"],
                "direction": score_data["direction"],
                "pattern": score_data["pattern"],
                "score": score_data["score"]
            }
            log_hook(f"Entered trade: {active_trade}")
            trade_count += 1
            if trade_count >= 50:
                break

    with open("trade_log.json", "w") as f:
        json.dump(trade_log, f, indent=2)
