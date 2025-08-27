
# Robust Yahoo provider with safe ranges and chunked history
import pandas as pd
import yfinance as yf
from datetime import datetime, timedelta
from typing import Dict, Optional

SAFE_LIMITS = {
    "1m": {"period": "7d", "max_days": 7},
    "5m": {"period": "59d", "max_days": 59},
    "15m": {"period": "59d", "max_days": 59},
}

class YahooProvider:
    def __init__(self, symbol: str = "MES=F"):
        self.symbol = symbol

    def _download(self, symbol: str, period: str, interval: str) -> pd.DataFrame:
        df = yf.download(
            symbol,
            period=period,
            interval=interval,
            auto_adjust=False,
            progress=False,
            threads=False,
        )
        if df is None or df.empty:
            return pd.DataFrame()
        df = df.dropna().reset_index()
        ts_col = "Datetime" if "Datetime" in df.columns else ("Date" if "Date" in df.columns else None)
        if ts_col is None:
            return pd.DataFrame()
        df["timestamp"] = pd.to_datetime(df[ts_col])
        keep = ["timestamp","Open","High","Low","Close","Volume"]
        df = df[[c for c in keep if c in df.columns]]
        return df

    def get_multi_timeframe_snapshot(self, interval: str = "1m") -> Dict[str, pd.DataFrame]:
        # Respect Yahoo limits
        plan = [("1m", SAFE_LIMITS["1m"]["period"]), ("5m", SAFE_LIMITS["5m"]["period"]), ("15m", SAFE_LIMITS["15m"]["period"])]
        out: Dict[str, pd.DataFrame] = {}
        for iv, period in plan:
            try:
                out[iv] = self._download(self.symbol, period, iv)
            except Exception:
                out[iv] = pd.DataFrame(columns=["timestamp","Open","High","Low","Close","Volume"])
        return out

    def get_intraday_history(self, symbol: Optional[str], interval: str, start_iso: str, end_iso: str) -> pd.DataFrame:
        """Chunked download between start and end using yfinance constraints."""
        symbol = symbol or self.symbol
        if interval not in SAFE_LIMITS:
            interval = "1m"
        # Parse times (assume input ISO-like without seconds ok)
        def parse(t):
            # allow "YYYY-MM-DDTHH:MM" or ISO
            try:
                return datetime.fromisoformat(t.replace("Z",""))
            except Exception:
                return None
        start = parse(start_iso)
        end = parse(end_iso)
        if not start or not end or end <= start:
            # default to last 5 days
            end = datetime.utcnow()
            start = end - timedelta(days=5)

        max_days = SAFE_LIMITS[interval]["max_days"]
        frames = []
        cur_start = start
        while cur_start < end:
            cur_end = min(cur_start + timedelta(days=max_days), end)
            # yfinance doesn't support arbitrary start/end for intraday on download() reliably for 1m;
            # we'll use period-based calls around the window, then trim.
            period_days = (cur_end - cur_start).days or 1
            # pick a safe period that covers the chunk
            if interval == "1m":
                period = "7d"
            else:
                period = f"{min(max_days, max(1, period_days))}d"

            try:
                chunk = yf.download(
                    symbol,
                    period=period,
                    interval=interval,
                    auto_adjust=False,
                    progress=False,
                    threads=False,
                )
                if chunk is not None and not chunk.empty:
                    chunk = chunk.dropna().reset_index()
                    ts_col = "Datetime" if "Datetime" in chunk.columns else ("Date" if "Date" in chunk.columns else None)
                    if ts_col:
                        chunk["timestamp"] = pd.to_datetime(chunk[ts_col])
                        chunk = chunk[(chunk["timestamp"] >= cur_start) & (chunk["timestamp"] <= cur_end)]
                        keep = ["timestamp","Open","High","Low","Close","Volume"]
                        chunk = chunk[[c for c in keep if c in chunk.columns]]
                        frames.append(chunk)
            except Exception:
                pass
            cur_start = cur_end

        if not frames:
            return pd.DataFrame(columns=["timestamp","Open","High","Low","Close","Volume"])
        df = pd.concat(frames, ignore_index=True).drop_duplicates(subset=["timestamp"]).sort_values("timestamp").reset_index(drop=True)
        return df
