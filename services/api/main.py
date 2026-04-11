from __future__ import annotations
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from config import settings
from routers import analysis, search, docs

logging.basicConfig(level=logging.INFO)

@asynccontextmanager
async def lifespan(app: FastAPI):
    yield

app = FastAPI(title="CodeLens API", version="0.1.0", lifespan=lifespan)

app.add_middleware(CORSMiddleware, allow_origins=settings.cors_origins,
                   allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

app.include_router(analysis.router, prefix="/api/analysis", tags=["analysis"])
app.include_router(search.router,   prefix="/api/search",   tags=["search"])
app.include_router(docs.router,     prefix="/api/docs",     tags=["docs"])

@app.get("/health")
async def health() -> dict:
    return {"status": "ok", "version": "0.1.0"}
