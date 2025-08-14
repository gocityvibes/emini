# trading_bot/datetime_fix.py - Fix datetime serialization for AI API calls

import json
from datetime import datetime
from typing import Any, Dict, List, Union

class DateTimeEncoder(json.JSONEncoder):
    """Custom JSON encoder that converts datetime objects to ISO strings"""
    def default(self, obj):
        if isinstance(obj, datetime):
            return obj.isoformat()
        return super().default(obj)

def clean_for_ai(data: Any) -> Any:
    """
    Recursively clean data to remove/convert datetime objects for AI API calls
    
    Args:
        data: Any data structure that might contain datetime objects
        
    Returns:
        Cleaned data with datetime objects converted to strings
    """
    if isinstance(data, dict):
        return {key: clean_for_ai(value) for key, value in data.items()}
    elif isinstance(data, list):
        return [clean_for_ai(item) for item in data]
    elif isinstance(data, datetime):
        return data.isoformat()
    elif hasattr(data, '__dict__'):
        # Handle objects with attributes
        return clean_for_ai(data.__dict__)
    else:
        return data

def serialize_market_data(market_data: Dict[str, Any]) -> str:
    """
    Serialize market data for AI API calls, handling datetime objects
    
    Args:
        market_data: Dictionary containing market information
        
    Returns:
        JSON string safe for AI API calls
    """
    try:
        cleaned_data = clean_for_ai(market_data)
        return json.dumps(cleaned_data, cls=DateTimeEncoder, ensure_ascii=False)
    except Exception as e:
        # Fallback: strip problematic fields
        safe_data = {}
        for key, value in market_data.items():
            try:
                json.dumps(value)
                safe_data[key] = value
            except (TypeError, ValueError):
                # Skip fields that can't be serialized
                if isinstance(value, datetime):
                    safe_data[key] = value.isoformat()
                else:
                    safe_data[key] = str(value)
        return json.dumps(safe_data)

def patch_openai_calls():
    """
    Monkey patch to automatically clean data before OpenAI API calls
    Call this once at startup to enable automatic datetime cleaning
    """
    import openai
    
    # Store original create method
    original_create = openai.chat.completions.create
    
    def patched_create(*args, **kwargs):
        # Clean messages before sending
        if 'messages' in kwargs:
            kwargs['messages'] = clean_for_ai(kwargs['messages'])
        return original_create(*args, **kwargs)
    
    # Replace with patched version
    openai.chat.completions.create = patched_create

# Auto-apply patch when imported
try:
    patch_openai_calls()
    print("✅ DateTime serialization patch applied successfully")
except Exception as e:
    print(f"⚠️ Could not apply datetime patch: {e}")
