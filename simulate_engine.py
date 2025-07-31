import pandas as pd
import numpy as np

def generate_price_series(start_price=4000.0, steps=60, volatility=0.002):
    prices = [start_price]
    for _ in range(steps - 1):
        prices.append(prices[-1] * (1 + np.random.normal(0, volatility)))
    return prices

def generate_simulated_candles(symbol, start_time, bars=1, interval_seconds=60, start_price=4000.0):
    timestamps = pd.date_range(start=start_time, periods=bars, freq=f'{interval_seconds}s')
    prices = generate_price_series(start_price=start_price, steps=bars + 1)
    data = {
        "Datetime": timestamps,
        "Open": prices[:-1],
        "High": [max(o, c) + np.random.rand() * 5 for o, c in zip(prices[:-1], prices[1:])],
        "Low": [min(o, c) - np.random.rand() * 5 for o, c in zip(prices[:-1], prices[1:])],
        "Close": prices[1:],
        "Volume": np.random.randint(100, 500, size=bars)
    }
    return pd.DataFrame(data)