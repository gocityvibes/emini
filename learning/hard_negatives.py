
# Minimal, safe replacement for learning.hard_negatives
# Avoids syntax errors during import. Replace with real logic later.

from typing import Any, Dict, List

class HardNegativeStore:
    def __init__(self) -> None:
        self._items: List[Dict[str, Any]] = []

    def record(self, item: Dict[str, Any]) -> None:
        self._items.append(item)

    def count(self) -> int:
        return len(self._items)

    def all(self) -> List[Dict[str, Any]]:
        return list(self._items)

# Backwards-friendly aliases some codebases expect
HardNegatives = HardNegativeStore

def record_hard_negative(*args, **kwargs):
    # No-op placeholder
    return None
