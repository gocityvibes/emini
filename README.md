# mes-scalper-api (Phase 3 enabled, prod)

Deploy on Render:
1) Push to GitHub.
2) Render → Clear build cache → Deploy latest commit.
3) Health: `/health` — OK; Phase status: `/phase` (if you keep that route).

Notes:
- Python 3.13.4 + numpy 2.3.2 (wheel).
- `learning/__init__.py` now exports FeedbackLoop, HardNegatives, PatternMemory.
- `learning/hard_negatives.py` fixed: completed `_extract_and_bin_features` + `_bin_value` (no placeholders).
