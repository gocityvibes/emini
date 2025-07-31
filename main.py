# main.py - FastAPI interface for sim broker control
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from live_runner import start_bot, stop_bot, get_summary, is_running

app = FastAPI()
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

@app.get("/start-bot")
def start():
    if is_running():
        return {"status": "already running"}
    start_bot()
    return {"status": "started"}

@app.get("/stop-bot")
def stop():
    stop_bot()
    return {"status": "stopped"}

@app.get("/status")
def status():
    return {"running": is_running()}

@app.get("/trade-summary")
def summary():
    return get_summary()