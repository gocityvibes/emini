import yfinance as yf
import pandas as pd

def fetch_ohlcv(symbol: str, period: str = "7d", interval: str = "1m") -> pd.DataFrame:
    """Fetch OHLCV bars from Yahoo Finance. Returns a pandas DataFrame indexed by datetime."""
    try:
        df = yf.download(tickers=symbol, period=period, interval=interval, progress=False, auto_adjust=False)
        # yfinance sometimes returns empty or columns with multiindex; normalize
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = [c[0] for c in df.columns]
        return df
    except Exception:
        return pd.DataFrame()
