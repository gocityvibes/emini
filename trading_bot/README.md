# AI Trading Bot - GPT-5 Integration

A sophisticated MES (Micro E-mini S&P 500) scalping bot powered by GPT-5 for trade decisions and continuous learning.

## Features

- **GPT-5 Decision Engine**: AI makes all entry/exit decisions with SL/TP
- **Hybrid Mode**: Optional GPT-4.1 pre-filtering for efficiency  
- **Learning System**: Automatically improves prompts based on trade outcomes
- **Real-time WebSocket**: Live trade updates and status monitoring
- **A/B Testing**: Compare different trading strategies
- **Flexible Configuration**: Customizable contracts, directions, and profiles

## Environment Variables

```bash
# Required
OPENAI_API_KEY=your_openai_api_key_here

# AI Configuration
MODEL_NAME=gpt-5
PROMPT_UPDATE_INTERVAL=25

# Hybrid Mode (Optional)
HYBRID_ENABLED=true
FT_MODEL_NAME_41=ft:gpt-4.1-mini:org:model:xxxx
HYBRID_SCORE_THRESHOLD=80.0

# Database
MONGODB_URL=mongodb://localhost:27017
DATABASE_NAME=trading_bot

# API
API_HOST=0.0.0.0
API_PORT=8000
```

## Installation

```bash
# Install dependencies
pip install -r trading_bot/requirements.txt

# Set environment variables
export OPENAI_API_KEY="your_key_here"
export MONGODB_URL="mongodb://localhost:27017"
```
