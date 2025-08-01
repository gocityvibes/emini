
import pandas as pd
from datetime import datetime, timedelta
import pytz
import os

def compute_indicators(df):
    """Compute technical indicators with proper error handling"""
    if len(df) < 26:  # Need at least 26 periods for MACD
        return df

    # Simple moving averages for EMA approximation
    df['EMA_8'] = df['Close'].ewm(span=8, adjust=False).mean()
    df['EMA_21'] = df['Close'].ewm(span=21, adjust=False).mean()

    # RSI calculation
    delta = df['Close'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
    rs = gain / loss
    df['RSI'] = 100 - (100 / (1 + rs))

    # MACD calculation
    ema12 = df['Close'].ewm(span=12, adjust=False).mean()
    ema26 = df['Close'].ewm(span=26, adjust=False).mean()
    macd = ema12 - ema26
    signal = macd.ewm(span=9, adjust=False).mean()
    df['MACD_Hist'] = macd - signal

    # VWAP approximation
    df['VWAP'] = df['Close'].rolling(20).mean()

    # ATR calculation
    df['ATR'] = (df['High'] - df['Low']).rolling(14).mean()

    return df

def score_trade_with_gpt4o(indicators):
    """Simplified scoring logic"""
    try:
        if indicators['EMA_8'] > indicators['EMA_21'] and indicators['MACD_Hist'] > 0:
            return {
                'pattern': 'Bullish EMA + MACD',
                'direction': 'long',
                'score': 95,
                'reason': 'EMA_8 > EMA_21 and MACD_Hist > 0'
            }
        elif indicators['EMA_8'] < indicators['EMA_21'] and indicators['MACD_Hist'] < 0:
            return {
                'pattern': 'Bearish EMA + MACD',
                'direction': 'short',
                'score': 93,
                'reason': 'EMA_8 < EMA_21 and MACD_Hist < 0'
            }
        else:
            return {
                'pattern': 'No clear signal',
                'direction': 'none',
                'score': 70,
                'reason': 'Neutral indicator setup'
            }
    except Exception as e:
        print(f"Error in scoring: {e}")
        return {
            'pattern': 'Error',
            'direction': 'none',
            'score': 0,
            'reason': 'Scoring error'
        }

def chrome_filter(df, indicators):
    """Chrome filter - placeholder"""
    return True

def shadow_filter(df, indicators):
    """Shadow filter - placeholder"""
    return True

def iron_curtain_filter(current_time, news_flags=None):
    """Iron curtain filter - placeholder"""
    return True

from mock_broker import MockTradeStationBroker
from simulate_engine import generate_simulated_candles
from sim_broker_interface import sim_place_ts_order, sim_get_open_position, sim_close_position, sim_apply_trailing_stop

# Simulation parameters
SIM_SYMBOL = "MES=F"
SIM_START_DATETIME = datetime(2025, 7, 1, 9, 30, tzinfo=pytz.timezone('US/Eastern'))
SIM_START_PRICE = 4900.00
SIM_CANDLES_PER_DAY = 390
TOTAL_SIM_DAYS = 5
SIM_INTERVAL_MINUTES = 1
TRAIL_AMOUNT = 5.00
GPT_SCORE_THRESHOLD = 95
MAX_TRADES = 50

# Global mock broker instance
mock_broker = MockTradeStationBroker(initial_balance=100000.0)

def run_full_simulation(log_hook=None):
    """Main simulation runner with fixed logic"""
    print("Starting full trading simulation...")
    trade_count = 0
    global_df = pd.DataFrame()

    try:
        for day_offset in range(TOTAL_SIM_DAYS):
            if trade_count >= MAX_TRADES:
                print(f"Maximum trades ({MAX_TRADES}) reached. Stopping simulation.")
                break

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
                if trade_count >= MAX_TRADES:
                    break

                current_candle = day_candles.iloc[[i]]
                current_sim_time = current_candle.index[0]
                mock_broker.set_sim_time(current_sim_time.strftime('%Y-%m-%d %H:%M'))

                global_df = pd.concat([global_df, current_candle])
                mock_broker.update_quote(SIM_SYMBOL, current_candle['Close'].iloc[-1])

                if len(global_df) < 30:
                    continue

                df_with_indicators = compute_indicators(global_df.copy())
                if df_with_indicators.empty:
                    continue

                latest_row = df_with_indicators.iloc[-1]
                if latest_row.isnull().any():
                    continue

                latest_indicators = {
                    "price": latest_row['Close'],
                    "RSI": latest_row['RSI'],
                    "MACD_Hist": latest_row['MACD_Hist'],
                    "EMA_8": latest_row['EMA_8'],
                    "EMA_21": latest_row['EMA_21'],
                    "VWAP": latest_row['VWAP'],
                    "ATR": latest_row['ATR'],
                    "time": current_sim_time.strftime("%H:%M")
                }

                if not chrome_filter(df_with_indicators, latest_indicators):
                    continue
                if not shadow_filter(df_with_indicators, latest_indicators):
                    continue
                if not iron_curtain_filter(current_sim_time.strftime("%H:%M")):
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

                open_pos = sim_get_open_position(mock_broker, SIM_SYMBOL)

                if open_pos:
                    print(f"[{current_sim_time}] 🔄 Position open. Checking trailing stop...")
                    sim_apply_trailing_stop(
                        mock_broker,
                        SIM_SYMBOL,
                        open_pos['entry_price'],
                        TRAIL_AMOUNT,
                        open_pos['side'],
                        open_pos['qty'],
                        SIM_INTERVAL_MINUTES * 60
                    )
                elif direction in ["long", "short"] and trade_count < MAX_TRADES:
                    print(f"[{current_sim_time}] ✅ Trade Signal: {direction.upper()} (Score: {score}) - {gpt4o_result.get('reason', '')}")

                    current_price = latest_indicators['price']
                    sim_qty = 1
                    atr = latest_indicators['ATR']

                    if direction == "long":
                        sim_side = "buy"
                        sim_stop_price = current_price - (atr * 2)
                        sim_limit_price = current_price + (atr * 4)
                    else:
                        sim_side = "sell"
                        sim_stop_price = current_price + (atr * 2)
                        sim_limit_price = current_price - (atr * 4)

                    trade_result = sim_place_ts_order(
                        mock_broker,
                        SIM_SYMBOL,
                        sim_side,
                        sim_qty,
                        sim_stop_price,
                        sim_limit_price
                    )

                    if trade_result["status"] == "submitted":
                        trade_count += 1
                        print(f"[{current_sim_time}] 📈 Trade #{trade_count} executed successfully")
                        if log_hook:
                            log_hook({
                                'symbol': SIM_SYMBOL,
                                'side': sim_side,
                                'timestamp': current_sim_time.isoformat(),
                                'reason': gpt4o_result.get('reason', 'N/A'),
                                'price': current_price,
                                'trade_number': trade_count
                            })
                    else:
                        print(f"[{current_sim_time}] 🚫 Trade Rejected: {trade_result.get('message', 'Unknown error')}")

    except Exception as e:
        print(f"Simulation error: {e}")
        import traceback
        traceback.print_exc()

    finally:
        print(f"\n--- Simulation Complete ---")
        print(f"Total trades executed: {trade_count}")
        print(f"Final balance: ${mock_broker.get_balance():.2f}")
        print(f"Net PnL: ${mock_broker.get_net_pnl():.2f}")
        if mock_broker.current_positions:
            print("Open positions:")
            for sym, pos in mock_broker.current_positions.items():
                print(f"  {sym}: {pos['side']} {pos['qty']} @ {pos['entry_price']:.2f}")
