# MES Scalper Training Backend

A Flask-based backend service for automated MES (E-mini S&P 500) futures scalping with GPT integration and comprehensive risk management.

## Purpose

This backend provides:
- Real-time market data from Yahoo Finance
- Technical analysis and prefiltering
- GPT-powered trade decisions with confidence calibration
- Realistic trade simulation with advanced risk management
- Learning system with pattern recognition and hard negatives
- RESTful API for frontend monitoring

## Setup

### Local Development

```bash
# Install dependencies
pip install -r requirements.txt

# Set environment variables
export OPENAI_API_KEY="your-openai-key"
export TIMEZONE="America/Chicago"
export DAILY_GPT_CALL_CAP=5
export DAILY_POINT_STOP=-3.0
export FRONTEND_CORS_ORIGIN="*"

# Run locally
python -m app.main
```

### Render Deployment

1. Create new Web Service on Render
2. Connect your repository
3. Set build command: `pip install -r requirements.txt`
4. Set start command: `gunicorn app.main:app --bind 0.0.0.0:$PORT`
5. Add environment variables in Render dashboard

### Required Environment Variables

- `OPENAI_API_KEY`: **REQUIRED** - Your OpenAI API key for GPT calls
- `TIMEZONE`: Trading timezone (default: America/Chicago)
- `DAILY_GPT_CALL_CAP`: Maximum GPT calls per day (default: 5)
- `DAILY_POINT_STOP`: Daily loss limit in points (default: -3.0)
- `FRONTEND_CORS_ORIGIN`: CORS origin for frontend (use * for development)

**⚠️ Critical:** The system will not function without `OPENAI_API_KEY` set in Phase 3.

## API Endpoints

### Phase 1: Core + Health

**GET /health**
```json
{
  "status": "ok",
  "server_time_utc": "2025-01-20T15:30:00Z",
  "server_time_ct": "2025-01-20T09:30:00"
}
```

**GET /metrics/summary**
```json
{
  "running": true,
  "trades_today": 3,
  "win_rate_trailing20": 85.5,
  "net_points_today": 1.75,
  "avg_time_to_target_sec": 45.2,
  "gpt_calls_used": 3,
  "gpt_calls_cap": 5
}
```

### Phase 2: Live Monitoring

**GET /metrics/live**
```json
{
  "setup_type": "ORB_retest_go",
  "direction": "long",
  "prefilter_score": 82,
  "volume_multiple": 2.1,
  "atr_5m": 1.2,
  "session_label": "rth_a",
  "timestamp_ct": "2025-01-20T09:45:00"
}
```

**GET /metrics/budget**
```json
{
  "calls_used": 3,
  "calls_cap": 5,
  "paused": false,
  "paused_reason": null
}
```

### Phase 3: Complete System

**POST /control/start**
**POST /control/stop**
```json
{
  "running": true
}
```

**GET /metrics/trades?date=2025-01-20**
```json
[
  {
    "result": "win",
    "prefilter_score": 82,
    "confidence": 88,
    "setup": "ORB_retest_go",
    "session": "rth_a",
    "entry_price": 5825.25,
    "exit_price": 5826.50,
    "pnl_pts": 1.25,
    "time_to_target": 42,
    "mae": -0.25,
    "mfe": 1.50
  }
]
```

**GET /metrics/fingerprints**
```json
[
  {
    "setup": "ORB_retest_go",
    "fingerprint_id": "orb_001",
    "status": "gold",
    "samples": 45,
    "win_rate": 84.4,
    "expectancy": 0.65
  }
]
```

## Architecture

- **app/main**: Flask application factory and orchestration
- **data/**: Market data providers and technical analysis
- **prefilter/**: Candidate filtering and confluence scoring
- **gpt/**: GPT integration, confidence calibration, rate limiting
- **learning/**: Feedback loops, pattern memory, hard negatives
- **simulation/**: Realistic trade execution with advanced risk management
- **api/**: REST endpoints for frontend integration

## Trading Rules (80% Win Rate System)

- **Sessions**: 08:30-10:30 CT and 13:00-15:00 CT only
- **Setups**: ORB retest-go, 20EMA pullback, VWAP rejection only
- **Filters**: Prefilter score ≥75, GPT confidence ≥85 (adaptive 82-92)
- **Risk**: TP +1.25, SL -0.75, BE at +0.50, trail after +1.00
- **Limits**: Max 6 trades/day, stop after 2 losses, daily stop -3.0 pts
- **Budget**: ≤5 GPT calls/day, batch every 30 seconds

## Data Flow

1. **Market Data**: Yahoo Finance → Technical indicators
2. **Prefilter**: Score candidates → Filter by thresholds
3. **GPT Decision**: High-scoring candidates → Trade/skip decision
4. **Execution**: Simulate realistic fills with slippage/commission
5. **Learning**: Trade results → Pattern memory + hard negatives
6. **Calibration**: Win rate feedback → Adjust confidence thresholds