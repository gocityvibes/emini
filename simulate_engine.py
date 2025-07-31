import pandas as pd
import numpy as np
from datetime import timedelta

def generate_simulated_candles(symbol, start_datetime, num_candles, interval_minutes, start_price,
                                volatility=0.00005, drift=0.000001, trend_strength=0.00001, chop_strength=0.00005):
    """
    Generates simulated OHLCV candles for a symbol over time.
    This creates realistic micro-trends, chop, and volatility.

    :param symbol: str - Symbol to simulate
    :param start_datetime: datetime - Starting time
    :param num_candles: int - Number of candles to generate
    :param interval_minutes: int - Time between candles
    :param start_price: float - Starting price
    :param volatility: float - Random noise factor
    :param drift: float - Overall market drift
    :param trend_strength: float - Trend component
    :param chop_strength: float - Noise/chop component
    :return: DataFrame of candles indexed by datetime
    """
    timestamps = [start_datetime + timedelta(minutes=i * interval_minutes) for i in range(num_candles)]
    prices = [start_price]

    for _ in range(1, num_candles):
        random_shock = np.random.normal(loc=drift, scale=volatility)
        trend_component = trend_strength * np.random.randn()
        chop_component = chop_strength * np.random.randn()
        change_pct = random_shock + trend_component + chop_component
        prices.append(prices[-1] * (1 + change_pct))

    df = pd.DataFrame(index=pd.to_datetime(timestamps))
    df["Open"] = prices[:-1]
    df["Close"] = prices[1:]
    df["High"] = np.maximum(df["Open"], df["Close"]) + np.random.rand(len(df)) * 0.25
    df["Low"] = np.minimum(df["Open"], df["Close"]) - np.random.rand(len(df)) * 0.25
    df["Volume"] = np.random.randint(100, 1000, size=len(df))

    return df