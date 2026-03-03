"""
main.py — FastAPI backend for BI Agent v2.
Endpoints:
  POST /api/query   — main query endpoint (text or voice-transcribed text)
  GET  /api/health  — health check
  GET  /api/schema  — return slim schema for debugging
"""

from fastapi import FastAPI, HTTPException, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
import uvicorn

from pipeline import run_pipeline
from tools import get_slim_schema, get_full_schema, test_db
from agents import transcribe_audio

from pipeline import run_pipeline
from tools import get_slim_schema, get_full_schema, test_db

app = FastAPI(title="BI Agent v2", version="2.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ─── Models ───────────────────────────────────────────────────────────────────

class QueryRequest(BaseModel):
    question: str


# ─── Endpoints ────────────────────────────────────────────────────────────────

@app.get("/api/health")
async def health():
    ok, msg = test_db()
    return {"status": "ok" if ok else "error", "db": msg, "version": "2.0.0"}


@app.get("/api/schema")
async def schema(full: bool = False):
    """Returns slim schema by default. Pass ?full=true for full schema."""
    data = get_full_schema() if full else get_slim_schema()
    return {"schema": data}


@app.post("/api/schema/refresh")
async def schema_refresh():
    """Bust schema cache and reload from DB."""
    from tools import bust_schema_cache
    bust_schema_cache()
    slim = get_slim_schema(force_refresh=True)
    return {"status": "refreshed", "chars": len(slim)}


@app.post("/api/query")
async def query(req: QueryRequest):
    if not req.question or not req.question.strip():
        raise HTTPException(status_code=400, detail="Question cannot be empty")

    result = await run_pipeline(req.question.strip())

    return {
        "sql":         result["sql"],
        "chart_spec":  result["chart_spec"],
        "insights":    result["insights"],
        "explanation": result["explanation"],
        "data":        result["data"],
        "columns":     result["columns"],
        "row_count":   result["row_count"],
        "error":       result["error"],
    }


@app.post("/api/transcribe")
async def transcribe(audio: UploadFile = File(...)):
    """Receive audio from browser MediaRecorder, return Gemini transcript."""
    audio_bytes = await audio.read()
    mime_type   = audio.content_type or "audio/webm"
    result      = await transcribe_audio(audio_bytes, mime_type)
    return result


# ─── Static files (serve index.html) ─────────────────────────────────────────

app.mount("/", StaticFiles(directory="static", html=True), name="static")


if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)