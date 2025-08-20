"""
Session Validator
Validates trading sessions and market hours for MES scalping system.
"""

from datetime import datetime, time
import pytz
from typing import Dict, Tuple, Optional
import pandas as pd


class SessionValidator:
    """
    Validates trading sessions based on configuration rules.
    
    Features:
    - RTH session validation (08:30-10:30, 13:00-15:00 CT)
    - Lunch block enforcement (10:30-13:00 CT)
    - Weekend/holiday detection
    - DST awareness
    - Tradable window determination
    
    Note: News guard is handled separately in news_guard module.
    """
    
    def __init__(self, config: Dict):
        """
        Initialize with session configuration.
        
        Args:
            config: Configuration dict containing sessions settings
        """
        self.config = config
        self.ct_tz = pytz.timezone(config['meta']['timezone'])
        self.utc_tz = pytz.UTC
        
        # Parse session times from config
        self.sessions = self._parse_session_times(config['sessions'])
        
    def _parse_session_times(self, sessions_config: Dict) -> Dict:
        """
        Parse session time strings into time objects.
        
        Args:
            sessions_config: Sessions section from config
            
        Returns:
            Dict with parsed time objects
        """
        sessions = {}
        
        # Parse RTH A (morning session)
        rth_a = sessions_config['rth_a'].split('-')
        sessions['rth_a_start'] = self._parse_time(rth_a[0])
        sessions['rth_a_end'] = self._parse_time(rth_a[1])
        
        # Parse RTH B (afternoon session)  
        rth_b = sessions_config['rth_b'].split('-')
        sessions['rth_b_start'] = self._parse_time(rth_b[0])
        sessions['rth_b_end'] = self._parse_time(rth_b[1])
        
        # Parse lunch block
        lunch = sessions_config['block_lunch'].split('-')
        sessions['lunch_start'] = self._parse_time(lunch[0])
        sessions['lunch_end'] = self._parse_time(lunch[1])
        
        return sessions
    
    def _parse_time(self, time_str: str) -> time:
        """Parse time string (HH:MM) into time object."""
        hour, minute = map(int, time_str.split(':'))
        return time(hour, minute)
    
    def _to_ct_time(self, utc_timestamp: datetime) -> datetime:
        """Convert UTC timestamp to CT."""
        if utc_timestamp.tzinfo is None:
            utc_timestamp = self.utc_tz.localize(utc_timestamp)
        return utc_timestamp.astimezone(self.ct_tz)
    
    def _is_weekend(self, dt: datetime) -> bool:
        """Check if timestamp falls on weekend."""
        return dt.weekday() >= 5  # Saturday=5, Sunday=6
    
    def _is_holiday(self, dt: datetime) -> bool:
        """
        Check if timestamp falls on a major US market holiday.
        
        Note: This is a simplified check. For production, consider using
        a proper holiday calendar like pandas_market_calendars.
        """
        # Major holidays when futures markets are closed
        # New Year's Day, Martin Luther King Jr. Day, Presidents Day,
        # Good Friday, Memorial Day, Independence Day, Labor Day,
        # Thanksgiving, Christmas Day
        
        year = dt.year
        month = dt.month
        day = dt.day
        
        # Simple holiday checks (not exhaustive)
        major_holidays = [
            (1, 1),   # New Year's Day
            (7, 4),   # Independence Day  
            (12, 25), # Christmas Day
        ]
        
        return (month, day) in major_holidays
    
    def validate_session(self, timestamp: datetime) -> Dict[str, bool]:
        """
        Validate trading session for given timestamp.
        
        Args:
            timestamp: UTC or timezone-aware datetime
            
        Returns:
            Dict with session validation flags
        """
        # Convert to CT
        ct_time = self._to_ct_time(timestamp)
        current_time = ct_time.time()
        
        # Weekend/holiday checks
        is_weekend = self._is_weekend(ct_time)
        is_holiday = self._is_holiday(ct_time)
        
        # Session time checks
        in_rth_a = (self.sessions['rth_a_start'] <= current_time <= self.sessions['rth_a_end'])
        in_rth_b = (self.sessions['rth_b_start'] <= current_time <= self.sessions['rth_b_end'])
        in_lunch_block = (self.sessions['lunch_start'] <= current_time <= self.sessions['lunch_end'])
        
        # Overall tradable determination
        tradable_now = (
            not is_weekend and 
            not is_holiday and 
            (in_rth_a or in_rth_b) and 
            not in_lunch_block
        )
        
        return {
            'in_rth_a': in_rth_a,
            'in_rth_b': in_rth_b, 
            'in_lunch_block': in_lunch_block,
            'is_weekend': is_weekend,
            'is_holiday': is_holiday,
            'tradable_now': tradable_now,
            'current_session': self._get_current_session(in_rth_a, in_rth_b, in_lunch_block),
            'ct_time': ct_time.strftime('%H:%M:%S'),
            'ct_date': ct_time.strftime('%Y-%m-%d')
        }
    
    def _get_current_session(self, in_rth_a: bool, in_rth_b: bool, in_lunch_block: bool) -> str:
        """Determine current session label."""
        if in_rth_a:
            return 'rth_a'
        elif in_rth_b:
            return 'rth_b'
        elif in_lunch_block:
            return 'lunch_block'
        else:
            return 'outside_hours'
    
    def get_session_boundaries(self, date: datetime) -> Dict[str, datetime]:
        """
        Get session boundary timestamps for a given date.
        
        Args:
            date: Date to get session boundaries for
            
        Returns:
            Dict with UTC timestamps for session starts/ends
        """
        # Create CT datetime objects for the date
        ct_date = self._to_ct_time(date).date()
        
        boundaries = {}
        
        # RTH A boundaries
        rth_a_start_ct = self.ct_tz.localize(
            datetime.combine(ct_date, self.sessions['rth_a_start'])
        )
        rth_a_end_ct = self.ct_tz.localize(
            datetime.combine(ct_date, self.sessions['rth_a_end'])
        )
        
        # RTH B boundaries  
        rth_b_start_ct = self.ct_tz.localize(
            datetime.combine(ct_date, self.sessions['rth_b_start'])
        )
        rth_b_end_ct = self.ct_tz.localize(
            datetime.combine(ct_date, self.sessions['rth_b_end'])
        )
        
        # Convert to UTC
        boundaries = {
            'rth_a_start_utc': rth_a_start_ct.astimezone(self.utc_tz),
            'rth_a_end_utc': rth_a_end_ct.astimezone(self.utc_tz),
            'rth_b_start_utc': rth_b_start_ct.astimezone(self.utc_tz),
            'rth_b_end_utc': rth_b_end_ct.astimezone(self.utc_tz),
            'lunch_start_utc': rth_a_end_ct.astimezone(self.utc_tz),
            'lunch_end_utc': rth_b_start_ct.astimezone(self.utc_tz)
        }
        
        return boundaries
    
    def is_valid_trading_time(self, timestamp: datetime) -> bool:
        """
        Quick check if timestamp is in valid trading window.
        
        Args:
            timestamp: UTC or timezone-aware datetime
            
        Returns:
            True if valid for trading, False otherwise
        """
        validation = self.validate_session(timestamp)
        return validation['tradable_now']
    
    def get_next_trading_session(self, current_time: datetime) -> Optional[Dict]:
        """
        Get information about the next trading session.
        
        Args:
            current_time: Current UTC or timezone-aware datetime
            
        Returns:
            Dict with next session info or None if same day
        """
        ct_time = self._to_ct_time(current_time)
        current_time_only = ct_time.time()
        
        # Check if we're before RTH A
        if current_time_only < self.sessions['rth_a_start']:
            return {
                'session': 'rth_a',
                'starts_at': self.sessions['rth_a_start'].strftime('%H:%M'),
                'starts_in_minutes': self._minutes_until_time(ct_time, self.sessions['rth_a_start'])
            }
        
        # Check if we're in lunch block
        elif self.sessions['rth_a_end'] < current_time_only < self.sessions['rth_b_start']:
            return {
                'session': 'rth_b', 
                'starts_at': self.sessions['rth_b_start'].strftime('%H:%M'),
                'starts_in_minutes': self._minutes_until_time(ct_time, self.sessions['rth_b_start'])
            }
        
        # After market hours - next session is tomorrow
        elif current_time_only > self.sessions['rth_b_end']:
            return {
                'session': 'rth_a',
                'starts_at': 'tomorrow ' + self.sessions['rth_a_start'].strftime('%H:%M'),
                'starts_in_minutes': None  # Next day calculation more complex
            }
        
        return None  # Currently in trading session
    
    def _minutes_until_time(self, current_dt: datetime, target_time: time) -> int:
        """Calculate minutes until target time on same day."""
        target_dt = current_dt.replace(
            hour=target_time.hour, 
            minute=target_time.minute, 
            second=0, 
            microsecond=0
        )
        delta = target_dt - current_dt
        return int(delta.total_seconds() / 60)


# Edge cases and behavior notes:
"""
DST Changes:
- pytz handles DST transitions automatically
- Session times remain constant in CT (08:30, 10:30, 13:00, 15:00)
- UTC conversion adjusts for DST spring forward/fall back

Holiday Closures:
- Current implementation has basic holiday detection
- For production, integrate pandas_market_calendars for complete accuracy
- Futures markets may have different holiday schedules than stock markets

Weekend Handling:
- Saturday/Sunday are automatically blocked
- Sunday evening futures trading not considered in this implementation
- Could be extended for 24/5 futures trading if needed

Session Validation Return Example:
{
    'in_rth_a': True,
    'in_rth_b': False,
    'in_lunch_block': False,
    'is_weekend': False,
    'is_holiday': False,
    'tradable_now': True,
    'current_session': 'rth_a',
    'ct_time': '09:15:30',
    'ct_date': '2025-01-20'
}

Session Boundaries Example:
{
    'rth_a_start_utc': datetime(2025, 1, 20, 14, 30, tzinfo=UTC),  # 08:30 CT
    'rth_a_end_utc': datetime(2025, 1, 20, 16, 30, tzinfo=UTC),    # 10:30 CT  
    'rth_b_start_utc': datetime(2025, 1, 20, 19, 0, tzinfo=UTC),   # 13:00 CT
    'rth_b_end_utc': datetime(2025, 1, 20, 21, 0, tzinfo=UTC),     # 15:00 CT
    'lunch_start_utc': datetime(2025, 1, 20, 16, 30, tzinfo=UTC),  # 10:30 CT
    'lunch_end_utc': datetime(2025, 1, 20, 19, 0, tzinfo=UTC)      # 13:00 CT
}

Usage:
validator = SessionValidator(config)
is_tradable = validator.is_valid_trading_time(datetime.utcnow())
session_info = validator.validate_session(datetime.utcnow())
"""