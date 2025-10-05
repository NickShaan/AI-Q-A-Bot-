# app/main.py
import os
import asyncio
import logging
import importlib
from typing import Optional

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("qna-api")

# Gemeni client
from app.services.ai_client import ask_gemini_sync


db = None
save_qa = None
init_db = None

DB_NAME = os.getenv("DB_NAME", "")
print(f"[main] DB_NAME={DB_NAME or '(empty)'}")

if DB_NAME:
    print("[main] Attempting to import app.db ...")
    try:
        db_module = importlib.import_module("app.db")
        init_db = getattr(db_module, "init_db", None)
        save_qa = getattr(db_module, "save_qa", None)
        db = getattr(db_module, "database", None)
        logger.info("DB module loaded successfully.")
        print("[main] app.db imported OK")
    except Exception as e:
        logger.warning("DB import failed — running without DB: %s", e)
        print(f"[main] app.db import FAILED: {e}")
else:
    print("[main] DB not configured (DB_NAME empty). Running without DB.")

app = FastAPI(title="Tiny Q&A API (Gemini)")

# CORS
ALLOWED_ORIGINS = ["http://localhost:4200", "http://127.0.0.1:4200"]
frontend_url = os.getenv("FRONTEND_URL")
if frontend_url:
    ALLOWED_ORIGINS.append(frontend_url)

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class AskRequest(BaseModel):
    question: str

class AskResponse(BaseModel):
    answer: str
    source: Optional[str] = "gemini"

@app.on_event("startup")
async def startup_event():
    print("[startup] Enter")
    logger.info("Starting Tiny Q&A API")

    # 1) Ensure tables (sync DDL)
    if init_db:
        try:
            print("[startup] Calling init_db() ...")
            init_db()
            print("[startup] init_db() OK")
        except Exception as e:
            logger.warning("init_db() failed: %s", e)
            print(f"[startup] init_db() FAILED: {e}")

    # 2) Connect async database
    if db:
        try:
            print("[startup] Connecting async database ...")
            await db.connect()
            logger.info("Connected to DB.")
            print("[startup] DB connected")
        except Exception as e:
            logger.warning("DB connection failed: %s", e)
            print(f"[startup] DB connect FAILED: {e}")

    print("[startup] Exit")

@app.on_event("shutdown")
async def shutdown_event():
    print("[shutdown] Enter")
    logger.info("Shutting down API")
    if db:
        try:
            print("[shutdown] Disconnecting DB ...")
            await db.disconnect()
            logger.info("DB disconnected.")
            print("[shutdown] DB disconnected")
        except Exception as e:
            logger.warning("DB disconnect failed: %s", e)
            print(f"[shutdown] DB disconnect FAILED: {e}")
    print("[shutdown] Exit")

@app.post("/ask", response_model=AskResponse)
async def ask(request: AskRequest):
    print("[/ask] Enter")
    q = (request.question or "").strip()
    if not q:
        print("[/ask] Empty question -> 400")
        raise HTTPException(status_code=400, detail="Question is required")

    try:
        print("[/ask] Calling ask_gemini_sync via to_thread ...")
        answer = await asyncio.to_thread(ask_gemini_sync, q)
        print("[/ask] Gemini answer received")
    except Exception as e:
        logger.exception("Gemini call failed: %s", e)
        print(f"[/ask] Gemini FAILED: {e}")
        raise HTTPException(status_code=502, detail="AI service error")

    if save_qa and db:
        try:
            print("[/ask] Saving to DB ...")
            inserted_id = await save_qa(q, answer)
            print(f"[/ask] Saved to DB (id={inserted_id})")
        except Exception as e:
            logger.warning("Save to DB failed: %s", e)
            print(f"[/ask] Save to DB FAILED: {e}")

    print("[/ask] Exit")
    return AskResponse(answer=answer, source="gemini")

@app.get("/health")
async def health():
    return {"status": "ok"}
