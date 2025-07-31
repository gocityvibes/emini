
# main_simulation_runner.py

import pandas as pd
from datetime import datetime, timedelta
import pytz
import os

from indicator_engine import compute_indicators
from phase_3_scoring_gpt4o import score_trade_with_gpt4o
from phase_4_filters import chrome_filter, shadow_filter, iron_curtain_filter

from mock_broker import MockTradeStationBroker
from simulate_engine import generate_simulated_candles
from sim_broker_interface import sim_place_ts_order, sim_get_open_position, sim_close_position, sim_apply_trailing_stop

SIM_SYMBOL = "MES=F"
SIM_START_DATETIME = datetime(2025, 7, 1, 9, 30, tzinfo=pytz.timezone('US/Eastern'))
SIM_START_PRICE = 4900.00
SIM_CANDLES_PER_DAY = 390
TOTAL_SIM_DAYS = 5
SIM_INTERVAL_MINUTES = 1
TRAIL_AMOUNT = 5.00
GPT_SCORE_THRESHOLD = 95

mock_broker = MockTradeStationBroker(initial_balance=100000.0)

def run_full_simulation():
    print("Starting full trading simulation...")
    global_df = pd.DataFrame()

    for day_offset in range(TOTAL_SIM_DAYS):
        current_day_start_dt = SIM_START_DATETIME + timedelta(days=day_offset)
        print(f"\n--- Simulating Day: {current_day_start_dt.strftime('%Y-%m-%d')} ---")

        day_candles = generate_simulated_candles(
            symbol=SIM_SYMBOL,
            start_datetime=current_day_start_dt,
            num_candles=SIM_CANDLES_PER_DAY,
            interval_minutes=SIM_INTERVAL_MINUTES,
            start_price=global_df['Close'].iloc[-1] if not global_df.empty else SIM_START_PRICE,
            volatility=0.00005, 
            drift=0.000001,
            trend_strength=0.00001,
            chop_strength=0.00005
        )

        for i in range(len(day_candles)):
            current_candle = day_candles.iloc[[i]]
            current_sim_time = current_candle.index[0]
            mock_broker.set_sim_time(current_sim_time.strftime('%Y-%m-%d %H:%M'))

            global_df = pd.concat([global_df, current_candle])
            mock_broker.update_quote(SIM_SYMBOL, current_candle['Close'].iloc[-1])

            if len(global_df) < 21:
                continue

            df_with_indicators = compute_indicators(global_df.copy())
            if df_with_indicators.empty or df_with_indicators.iloc[-1].isnull().any():
                continue

            latest_indicators = {
                "price": df_with_indicators['Close'].iloc[-1],
                "RSI": df_with_indicators['RSI'].iloc[-1],
                "MACD_Hist": df_with_indicators['MACD_Hist'].iloc[-1],
                "EMA_8": df_with_indicators['EMA_8'].iloc[-1],
                "EMA_21": df_with_indicators['EMA_21'].iloc[-1],
                "VWAP": df_with_indicators['VWAP'].iloc[-1],
                "ATR": df_with_indicators['ATR'].iloc[-1],
                "time": current_sim_time.strftime("%H:%M")
            }

            current_hour_minute = current_sim_time.strftime("%H:%M")
            news_flags_for_sim = {}

            if not chrome_filter(df_with_indicators, latest_indicators):
                continue
            if not shadow_filter(df_with_indicators, latest_indicators):
                continue
            if not iron_curtain_filter(current_hour_minute, news_flags=news_flags_for_sim):
                continue

            try:
                gpt4o_result = score_trade_with_gpt4o(latest_indicators)
            except Exception as e:
                print(f"[{current_sim_time}] GPT-4o Scoring Error: {e}")
                continue

            score = gpt4o_result.get("score", 0)
            direction = gpt4o_result.get("direction", "none")

            if score < GPT_SCORE_THRESHOLD:
                continue

            print(f"[{current_sim_time}] ✅ Potential Trade Signal for {SIM_SYMBOL}: {direction.upper()} (Score: {score}) - {gpt4o_result.get('reason', '')}")
            open_pos = sim_get_open_position(mock_broker, SIM_SYMBOL)

            if open_pos:
                print(f"[{current_sim_time}] 🔄 Position open. Checking sentinel...")
                sim_apply_trailing_stop(
                    mock_broker,
                    SIM_SYMBOL,
                    open_pos['entry_price'],
                    TRAIL_AMOUNT,
                    open_pos['side'],
                    open_pos['qty'],
                    SIM_INTERVAL_MINUTES * 60
                )
            elif direction in ["long", "short"]:
                current_price_for_order = latest_indicators['price']
                sim_qty = 1

                if direction == "long":
                    sim_side = "buy"
                    sim_stop_price = current_price_for_order - (latest_indicators['ATR'] * 2)
                    sim_limit_price = current_price_for_order + (latest_indicators['ATR'] * 4)
                elif direction == "short":
                    sim_side = "sell"
                    sim_stop_price = current_price_for_order + (latest_indicators['ATR'] * 2)
                    sim_limit_price = current_price_for_order - (latest_indicators['ATR'] * 4)
                else:
                    continue

                trade_result = sim_place_ts_order(
                    mock_broker,
                    SIM_SYMBOL,
                    sim_side,
                    sim_qty,
                    sim_stop_price,
                    sim_limit_price
                )

                if trade_result["status"] != "submitted":
                    print(f"[{current_sim_time}] 🚫 Simulated Order Rejected: {trade_result['message']}")

    print("\n--- Full Simulation Complete ---")
    print(f"Final Mock Broker Balance: ${mock_broker.get_balance():,.2f}")
    print(f"Total Net PnL: ${mock_broker.get_net_pnl():,.2f}")
    print(f"Total simulated entry/exit trades: {len(mock_broker.get_order_history())}")

if __name__ == "__main__":
    if os.getenv("OPENAI_API_KEY") is None:
        print("WARNING: OPENAI_API_KEY environment variable not set.")
    run_full_simulation()
