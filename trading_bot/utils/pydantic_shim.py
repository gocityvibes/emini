# trading_bot/utils/pydantic_shim.py
"""
Pydantic compatibility utilities for seamless model handling.
"""

from typing import Dict, Any, Type, TypeVar
from pydantic import BaseModel

T = TypeVar('T', bound=BaseModel)

def model_to_dict(model: BaseModel) -> Dict[str, Any]:
    """Convert Pydantic model to dictionary with proper serialization"""
    try:
        # Use model_dump for Pydantic v2
        return model.model_dump()
    except AttributeError:
        # Fallback to dict() for Pydantic v1 compatibility
        return model.dict()

def dict_to_model(data: Dict[str, Any], model_class: Type[T]) -> T:
    """Create Pydantic model instance from dictionary"""
    try:
        # Use model_validate for Pydantic v2
        return model_class.model_validate(data)
    except AttributeError:
        # Fallback to parse_obj for Pydantic v1 compatibility
        return model_class.parse_obj(data)

def model_json_schema(model_class: Type[BaseModel]) -> Dict[str, Any]:
    """Get JSON schema for Pydantic model"""
    try:
        # Use model_json_schema for Pydantic v2
        return model_class.model_json_schema()
    except AttributeError:
        # Fallback to schema for Pydantic v1 compatibility
        return model_class.schema()

def safe_model_dump(model: BaseModel, **kwargs) -> Dict[str, Any]:
    """Safely dump model to dictionary with error handling"""
    try:
        return model.model_dump(**kwargs)
    except AttributeError:
        try:
            return model.dict(**kwargs)
        except Exception as e:
            print(f"Warning: Failed to serialize model {type(model).__name__}: {e}")
            return {"error": f"Serialization failed: {e}"}
    except Exception as e:
        print(f"Warning: Failed to serialize model {type(model).__name__}: {e}")
        return {"error": f"Serialization failed: {e}"}
