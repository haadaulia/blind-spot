"""
app.py — BlindSpot web app (FastAPI).

Run:
    pip install fastapi uvicorn
    uvicorn app:app --reload
    open http://127.0.0.1:8000

Endpoints:
    GET /                       -> the interactive frontend
    GET /api/analyze?target=&peers=F,GM,RIVN  -> run (or load cached) analysis
    GET /api/presets            -> demo presets (Tesla vs autos, GS vs banks)
"""
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, JSONResponse

from pipeline import run_analysis

app = FastAPI(title="BlindSpot")
ROOT = Path(__file__).parent
STATIC = ROOT / "static"

PRESETS = [
    {"label": "Tesla vs legacy automakers", "target": "TSLA", "peers": ["F", "GM", "RIVN"],
     "note": "Structurally different — gaps expected"},
    {"label": "Goldman vs universal banks", "target": "GS", "peers": ["MS", "JPM", "BAC"],
     "note": "Near-identical peers — control, ~0 gaps"},
]


@app.get("/")
def home():
    return FileResponse(STATIC / "index.html")


@app.get("/api/presets")
def presets():
    return PRESETS


@app.get("/api/analyze")
def analyze(target: str, peers: str):
    peer_list = [p for p in peers.replace(" ", "").split(",") if p]
    if not target or not peer_list:
        raise HTTPException(400, "target and peers required")
    try:
        return JSONResponse(run_analysis(target, peer_list))
    except Exception as e:
        raise HTTPException(500, f"{type(e).__name__}: {e}")
