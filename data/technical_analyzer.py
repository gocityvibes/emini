"""
Technical Analysis Indicators
Calculates EMA, RSI, VWAP and other indicators across multiple timeframes.
"""

import pandas as pd
import numpy as np
from datetime import datetime, time
import pytz
from typing import Dict, Tuple, Optional


class TechnicalAnalyzer:
    """
    Multi-timeframe technical indicator calculations for MES scalping.
    
    Indicators:
    - EMA(20) on 1m, 5m, 15m
    - RSI(14) on all timeframes  
    - Session-based VWAP
    - 5m ATR for volatility
    - 1m Volume MA(20) and multiples
    
    Column naming convention:
    - EMA_20, RSI_14, VWAP, ATR_14
    - Volume_MA20, Volume_Multiple
    """
    
    def __init__(self, timezone: str = 'America/Chicago'):
        self.ct_tz = pytz.timezone(timezone)
        
    def calculate_ema(self, df: pd.DataFrame, period: int = 20, column: str = 'Close') -> pd.Series:
        """
        Calculate Exponential Moving Average.
        
        Args:
            df: OHLCV DataFrame
            period: EMA period
            column: Price column to use
            
        Returns:
            Series with EMA values
        """
        return df[column].ewm(span=period, adjust=False).mean()
    
    def calculate_rsi(self, df: pd.DataFrame, period: int = 14, column: str = 'Close') -> pd.Series:
        """
        Calculate RSI (Relative Strength Index).
        
        Args:
            df: OHLCV DataFrame  
            period: RSI period
            column: Price column to use
            
        Returns:
            Series with RSI values (0-100)
        """
        delta = df[column].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
        
        rs = gain / loss
        rsi = 100 - (100 / (1 + rs))
        return rsi
    
    def calculate_vwap(self, df: pd.DataFrame, session_start: time = None, session_end: time = None) -> pd.Series:
        """
        Calculate session-based VWAP (Volume Weighted Average Price).
        
        Args:
            df: OHLCV DataFrame with UTC timestamps
            session_start: Session start time in CT (e.g., time(8,30))
            session_end: Session end time in CT (e.g., time(10,30))
            
        Returns:
            Series with VWAP values
        """
        df_copy = df.copy()
        
        # Convert UTC index to CT for session filtering
        df_copy.index = df_copy.index.tz_convert(self.ct_tz)
        
        # If session times provided, filter to session only
        if session_start and session_end:
            session_mask = (df_copy.index.time >= session_start) & (df_copy.index.time <= session_end)
            df_session = df_copy[session_mask].copy()
        else:
            df_session = df_copy.copy()
        
        if df_session.empty:
            return pd.Series(index=df.index, dtype=float)
        
        # Calculate typical price
        df_session['TP'] = (df_session['High'] + df_session['Low'] + df_session['Close']) / 3
        df_session['TP_Volume'] = df_session['TP'] * df_session['Volume']
        
        # Cumulative sums for VWAP calculation
        df_session['Cum_TP_Volume'] = df_session['TP_Volume'].cumsum()
        df_session['Cum_Volume'] = df_session['Volume'].cumsum()
        
        # VWAP = Cumulative(TP * Volume) / Cumulative(Volume)
        vwap_session = df_session['Cum_TP_Volume'] / df_session['Cum_Volume']
        
        # Reindex to match original DataFrame
        vwap_full = pd.Series(index=df.index, dtype=float)
        
        # Convert back to UTC for alignment
        vwap_session.index = vwap_session.index.tz_convert('UTC')
        vwap_full.loc[vwap_session.index] = vwap_session
        
        # Forward fill VWAP within session
        vwap_full = vwap_full.fillna(method='ffill')
        
        return vwap_full
    
    def calculate_atr(self, df: pd.DataFrame, period: int = 14) -> pd.Series:
        """
        Calculate Average True Range.
        
        Args:
            df: OHLCV DataFrame
            period: ATR period
            
        Returns:
            Series with ATR values
        """
        high_low = df['High'] - df['Low']
        high_close_prev = abs(df['High'] - df['Close'].shift(1))
        low_close_prev = abs(df['Low'] - df['Close'].shift(1))
        
        true_range = pd.concat([high_low, high_close_prev, low_close_prev], axis=1).max(axis=1)
        atr = true_range.rolling(window=period).mean()
        
        return atr
    
    def add_all_indicators(self, df: pd.DataFrame, timeframe: str, session_times: Dict = None) -> pd.DataFrame:
        """
        Add all relevant indicators to a DataFrame.
        
        Args:
            df: OHLCV DataFrame
            timeframe: '1m', '5m', or '15m'
            session_times: Dict with 'start' and 'end' time objects for VWAP
            
        Returns:
            DataFrame with all indicators added
        """
        df_with_indicators = df.copy()
        
        if df.empty or len(df) < 20:
            return df_with_indicators
        
        # EMA(20)
        df_with_indicators['EMA_20'] = self.calculate_ema(df, period=20)
        
        # RSI(14)
        df_with_indicators['RSI_14'] = self.calculate_rsi(df, period=14)
        
        # VWAP (session-based if times provided)
        if session_times:
            df_with_indicators['VWAP'] = self.calculate_vwap(
                df, 
                session_start=session_times.get('start'),
                session_end=session_times.get('end')
            )
        else:
            df_with_indicators['VWAP'] = self.calculate_vwap(df)
        
        # ATR for 5m timeframe
        if timeframe == '5m':
            df_with_indicators['ATR_14'] = self.calculate_atr(df, period=14)
        
        # Volume indicators for 1m timeframe (if not already present)
        if timeframe == '1m' and 'Volume_MA20' not in df.columns:
            df_with_indicators['Volume_MA20'] = df['Volume'].rolling(window=20, min_periods=20).mean()
            df_with_indicators['Volume_Multiple'] = df_with_indicators['Volume'] / df_with_indicators['Volume_MA20']
        
        return df_with_indicators
    
    def align_multi_timeframe_indicators(self, data_dict: Dict[str, pd.DataFrame]) -> Dict[str, float]:
        """
        Align indicators from multiple timeframes to current decision point.
        
        Args:
            data_dict: Dict with '1m', '5m', '15m' DataFrames containing indicators
            
        Returns:
            Dict with latest synced indicator values
        """
        aligned = {}
        
        # Get latest timestamps from each timeframe
        latest_times = {}
        for tf, df in data_dict.items():
            if not df.empty:
                latest_times[tf] = df.index[-1]
        
        if not latest_times:
            return aligned
        
        # Use 1m as the reference timeframe
        ref_time = latest_times.get('1m')
        if ref_time is None:
            return aligned
        
        # Extract latest values for each timeframe
        for tf, df in data_dict.items():
            if df.empty:
                continue
                
            # Get the most recent row
            latest_row = df.iloc[-1]
            
            # Add timeframe prefix to indicator names
            for col in ['EMA_20', 'RSI_14', 'VWAP']:
                if col in df.columns and not pd.isna(latest_row[col]):
                    aligned[f'{tf}_{col}'] = latest_row[col]
            
            # Special cases
            if tf == '5m' and 'ATR_14' in df.columns and not pd.isna(latest_row['ATR_14']):
                aligned['ATR_5m'] = latest_row['ATR_14']
                
            if tf == '1m':
                for col in ['Volume_Multiple', 'Volume_MA20']:
                    if col in df.columns and not pd.isna(latest_row[col]):
                        aligned[f'1m_{col}'] = latest_row[col]
        
        # Add current price info
        if '1m' in data_dict and not data_dict['1m'].empty:
            latest_1m = data_dict['1m'].iloc[-1]
            aligned['current_price'] = latest_1m['Close']
            aligned['current_volume'] = latest_1m['Volume']
        
        # Add sync timestamp
        aligned['sync_timestamp_utc'] = ref_time.isoformat()
        
        return aligned


# Expected column names and units:
"""
Input DataFrame columns:
- Open, High, Low, Close (price in points, e.g., 5825.25)
- Volume (contracts)

Output indicator columns:
- EMA_20: Exponential moving average (price points)
- RSI_14: Relative strength index (0-100)
- VWAP: Volume weighted average price (price points)
- ATR_14: Average true range (price points, e.g., 1.25)
- Volume_MA20: 20-period volume moving average (contracts)
- Volume_Multiple: Volume vs MA20 ratio (e.g., 2.1 = 210%)

Alignment output example:
{
    '1m_EMA_20': 5825.75,
    '5m_EMA_20': 5826.00,
    '15m_EMA_20': 5824.50,
    '1m_RSI_14': 65.2,
    '5m_RSI_14': 58.7,
    '1m_VWAP': 5825.50,
    'ATR_5m': 1.25,
    '1m_Volume_Multiple': 2.1,
    'current_price': 5826.25,
    'sync_timestamp_utc': '2025-01-20T14:45:00+00:00'
}

Session times for VWAP:
- RTH A: time(8, 30) to time(10, 30) CT
- RTH B: time(13, 0) to time(15, 0) CT

Multi-timeframe alignment uses latest 1m timestamp as reference.
All indicators require minimum periods for calculation (20 for EMA, 14 for RSI/ATR).
"""