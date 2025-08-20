"""
Yahoo Finance Data Provider
Fetches and normalizes OHLCV data for MES=F with retry logic and data cleaning.
"""

import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import pytz
from tenacity import retry, stop_after_attempt, wait_exponential
from typing import Dict, Optional, List


class YahooProvider:
    """
    Data provider utility for fetching MES=F futures data from Yahoo Finance.
    
    Features:
    - Multi-timeframe data (1m, 5m, 15m)
    - Retry logic with exponential backoff
    - UTC normalization with CT presentation
    - Data cleaning (NaNs, ascending timestamps)
    - Volume MA(20) and ATR calculations
    """
    
    def __init__(self, symbol: str = 'MES=F', timezone: str = 'America/Chicago'):
        self.symbol = symbol
        self.ct_tz = pytz.timezone(timezone)
        self.utc_tz = pytz.UTC
        
    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=4, max=10))
    def _fetch_raw_data(self, period: str, interval: str) -> pd.DataFrame:
        """
        Fetch raw OHLCV data with retry logic.
        
        Args:
            period: Data period ('60d', '90d')
            interval: Timeframe ('1m', '5m', '15m')
            
        Returns:
            DataFrame with OHLCV columns and datetime index
        """
        ticker = yf.Ticker(self.symbol)
        data = ticker.history(period=period, interval=interval, prepost=True)
        
        if data.empty:
            raise ValueError(f"No data returned for {self.symbol}")
            
        return data
    
    def _clean_data(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Clean and normalize data.
        
        Args:
            df: Raw OHLCV DataFrame
            
        Returns:
            Cleaned DataFrame with UTC timestamps
        """
        # Remove NaN rows
        df = df.dropna()
        
        # Ensure index is datetime and convert to UTC
        if not isinstance(df.index, pd.DatetimeIndex):
            df.index = pd.to_datetime(df.index)
            
        # Convert to UTC if not already
        if df.index.tz is None:
            df.index = df.index.tz_localize('UTC')
        elif df.index.tz != self.utc_tz:
            df.index = df.index.tz_convert('UTC')
            
        # Ensure strictly ascending timestamps
        df = df.sort_index()
        df = df[~df.index.duplicated(keep='last')]
        
        # Standardize column names
        df.columns = ['Open', 'High', 'Low', 'Close', 'Volume']
        
        return df
    
    def _add_volume_ma(self, df: pd.DataFrame, period: int = 20) -> pd.DataFrame:
        """Add volume moving average."""
        df = df.copy()
        df['Volume_MA20'] = df['Volume'].rolling(window=period, min_periods=period).mean()
        df['Volume_Multiple'] = df['Volume'] / df['Volume_MA20']
        return df
    
    def _to_ct_string(self, utc_timestamp: pd.Timestamp) -> str:
        """Convert UTC timestamp to CT string for UI display."""
        ct_time = utc_timestamp.tz_convert(self.ct_tz)
        return ct_time.strftime('%Y-%m-%d %H:%M:%S')
    
    def fetch_timeframe_data(self, interval: str, days_back: int = 90) -> Dict:
        """
        Fetch data for a specific timeframe.
        
        Args:
            interval: '1m', '5m', or '15m'
            days_back: Number of days to fetch (60-90)
            
        Returns:
            Dict with keys: 'data' (DataFrame), 'latest_ct', 'row_count'
        """
        period = f"{days_back}d"
        
        try:
            raw_data = self._fetch_raw_data(period, interval)
            clean_data = self._clean_data(raw_data)
            
            # Add volume indicators for 1m data
            if interval == '1m':
                clean_data = self._add_volume_ma(clean_data)
            
            latest_utc = clean_data.index[-1] if not clean_data.empty else None
            latest_ct = self._to_ct_string(latest_utc) if latest_utc else None
            
            return {
                'data': clean_data,
                'latest_ct': latest_ct,
                'row_count': len(clean_data),
                'interval': interval,
                'symbol': self.symbol
            }
            
        except Exception as e:
            return {
                'data': pd.DataFrame(),
                'latest_ct': None,
                'row_count': 0,
                'interval': interval,
                'symbol': self.symbol,
                'error': str(e)
            }
    
    def get_latest_bars(self, interval: str, n_bars: int = 100) -> pd.DataFrame:
        """
        Get the most recent N bars for a timeframe.
        
        Args:
            interval: '1m', '5m', or '15m'
            n_bars: Number of recent bars to return
            
        Returns:
            DataFrame with most recent bars
        """
        data_result = self.fetch_timeframe_data(interval)
        df = data_result['data']
        
        if df.empty:
            return df
            
        return df.tail(n_bars)
    
    def get_multi_timeframe_snapshot(self) -> Dict:
        """
        Get current snapshot across all timeframes.
        
        Returns:
            Dict with '1m', '5m', '15m' keys containing recent data
        """
        snapshot = {}
        
        for interval in ['1m', '5m', '15m']:
            snapshot[interval] = self.get_latest_bars(interval, n_bars=200)
            
        return snapshot
    
    def calculate_atr(self, df_5m: pd.DataFrame, period: int = 14) -> float:
        """
        Calculate Average True Range from 5m data.
        
        Args:
            df_5m: 5-minute OHLCV DataFrame
            period: ATR period
            
        Returns:
            Latest ATR value or None if insufficient data
        """
        if len(df_5m) < period + 1:
            return None
            
        # True Range calculation
        high_low = df_5m['High'] - df_5m['Low']
        high_close_prev = abs(df_5m['High'] - df_5m['Close'].shift(1))
        low_close_prev = abs(df_5m['Low'] - df_5m['Close'].shift(1))
        
        true_range = pd.concat([high_low, high_close_prev, low_close_prev], axis=1).max(axis=1)
        atr = true_range.rolling(window=period).mean()
        
        return atr.iloc[-1] if not pd.isna(atr.iloc[-1]) else None


# Example usage and expected data shapes:
"""
Expected DataFrame structure after cleaning:

Index: DatetimeIndex (UTC timezone)
Columns: ['Open', 'High', 'Low', 'Close', 'Volume']

For 1m data, additional columns:
['Volume_MA20', 'Volume_Multiple']

Sample fetch_timeframe_data() output:
{
    'data': DataFrame with OHLCV data,
    'latest_ct': '2025-01-20 09:45:00',  # CT string for UI
    'row_count': 1440,  # Number of bars
    'interval': '1m',
    'symbol': 'MES=F'
}

Sample get_multi_timeframe_snapshot() output:
{
    '1m': DataFrame with last 200 1m bars,
    '5m': DataFrame with last 200 5m bars, 
    '15m': DataFrame with last 200 15m bars
}

ATR calculation returns float (e.g., 1.25) representing points.
Volume multiple shows ratio vs MA20 (e.g., 2.1 = 210% of average).
"""