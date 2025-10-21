# src/main.py
from __future__ import annotations

import logging
import os
import time
from pathlib import Path
from typing import Optional, List, Dict, Any, Callable

from fastapi import FastAPI, BackgroundTasks, HTTPException, Header, Body, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, FileResponse
from pydantic import BaseModel

from .settings import SETTINGS
from .embeddings import Embedder
from .vectordb import VectorDB
from .indexer import index_all
from src.agents.langchain_orchestrator import run_langchain_pipeline

# -------------------------------------------------
# App setup (API-only; UI handled by Next.js)
# -------------------------------------------------
OUT_DIR = Path("/app/out")

LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
logging.basicConfig(level=LOG_LEVEL, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("app")

app = FastAPI(title="UE Agentic Copilot API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=os.getenv("CORS_ORIGINS", "http://localhost:3000").split(","),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

EMB = Embedder(os.getenv("EMBEDDING_MODEL", "BAAI/bge-small-en"))
VDB = VectorDB()


class Ask(BaseModel):
    prompt: str


def _collection_count() -> int:
    try:
        return VDB.client.count(VDB.collection, exact=True).count
    except Exception:
        return 0


@app.on_event("startup")
def startup():
    t0 = time.perf_counter()
    policy = os.getenv("INDEX_ON_STARTUP", "auto").lower()
    logger.info("startup: policy=%s collection=%s", policy, VDB.collection)

    dim = getattr(EMB, "dim", 0) or 384
    VDB.ensure_collection(dim=dim, recreate_on_mismatch=True)

    existing = _collection_count()
    logger.info("startup: existing points in '%s' = %d", VDB.collection, existing)

    if policy == "never":
        logger.info("startup: skipping indexing (policy=never)")
        return
    if policy == "auto" and existing > 0:
        logger.info("startup: skipping indexing (policy=auto, collection non-empty)")
        return

    logger.info("startup: starting indexing run…")
    stats = index_all(
        unreal_docs=Path("/ingest/unreal_docs"),
        project=Path("/ingest/project"),
        plugins=Path("/ingest/plugins"),
        embedder=EMB,
        vdb=VDB,
        log=logging.getLogger("indexer"),
        log_every_files=100,
        log_every_chunks=1000,
    )
    logger.info(
        "startup: indexing done files=%s chunks=%s in %ss",
        stats.get("files"),
        stats.get("chunks"),
        stats.get("elapsed_s"),
    )
    logger.info("startup: finished in %.1fs", time.perf_counter() - t0)


# -------------------------------------------------
# Retrieval adapter for orchestrator
# -------------------------------------------------
def _retrieve_adapter(query: str, k: int = 60, top_n: int = 8) -> List[Dict[str, Any]]:
    qvec = EMB.embed([query])[0]
    hits = VDB.search(qvec, k=k, with_payload=True, with_vectors=False)

    q_terms = [w.lower() for w in query.split() if len(w) > 3]

    def boost(text: str) -> int:
        t = (text or "").lower()
        return sum(1 for w in q_terms if w in t)

    mapped: List[Dict[str, Any]] = []
    for h in hits:
        p = h.get("payload", {}) if isinstance(h, dict) else {}
        text = p.get("text", "") or ""
        mapped.append(
            {
                "id": h.get("id"),
                "score": float(h.get("score", 0.0)) + 0.01 * boost(text),
                "path": p.get("path") or p.get("file") or "",
                "source": p.get("source", ""),
                "text": text,
            }
        )

    min_score = float(os.getenv("RAG_MIN_SCORE", "0"))
    mapped = [m for m in mapped if m["score"] >= min_score]
    mapped.sort(key=lambda r: r["score"], reverse=True)
    return mapped[:top_n]


# -------------------------------------------------
# Public API
# -------------------------------------------------
@app.get("/health")
def health():
    return {"ok": True}


@app.post("/ask")
def ask(body: dict = Body(...)):
    prompt = (body.get("prompt") or "").strip()
    logger.info("/ask: prompt=%r", prompt)
    if not prompt:
        return JSONResponse(
            {"decision": "NO", "message": "Empty prompt"},
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    try:
        result = run_langchain_pipeline(prompt, retrieve_fn=_retrieve_adapter)
        ok = (result or {}).get("decision") == "YES"
        if not (result.get("markdown") or ""):
            logger.warning("/ask: empty markdown returned")
        return JSONResponse(result, status_code=status.HTTP_200_OK if ok else status.HTTP_200_OK)
    except Exception as e:
        logger.exception("/ask failed: %s", e)
        return JSONResponse({"decision": "NO", "message": str(e)}, status_code=500)


@app.post("/ingest")
def ingest(background: BackgroundTasks):
    """
    Trigger a full re-index in the background.
    """
    background.add_task(
        index_all,
        Path("/ingest/unreal_docs"),
        Path("/ingest/project"),
        Path("/ingest/plugins"),
        EMB,
        VDB,
        logging.getLogger("indexer"),
        100,
        1000,
    )
    return {"status": "started"}


@app.get("/download/{name}")
def download_md(name: str):
    if "/" in name or "\\" in name:
        raise HTTPException(status_code=400, detail="Invalid filename")
    path = OUT_DIR / name
    if not path.exists():
        raise HTTPException(status_code=404, detail="File not found")
    return FileResponse(str(path), media_type="text/markdown", filename=name)


# -------------------------------------------------
# Admin: reindex with token guard
# -------------------------------------------------
class ReindexState:
    running: bool = False
    last_started: float | None = None
    last_finished: float | None = None
    last_stats: dict | None = None
    last_error: str | None = None


STATE = ReindexState()


def _require_token(x_token: Optional[str]):
    expected = os.getenv("REINDEX_TOKEN")
    if not expected:
        return
    if not x_token or x_token != expected:
        raise HTTPException(status_code=401, detail="Invalid token")


def _reindex_task_sync():
    STATE.running = True
    STATE.last_error = None
    STATE.last_started = time.time()
    try:
        stats = index_all(
            unreal_docs=Path("/ingest/unreal_docs"),
            project=Path("/ingest/project"),
            plugins=Path("/ingest/plugins"),
            embedder=EMB,
            vdb=VDB,
            log=logging.getLogger("indexer"),
            log_every_files=100,
            log_every_chunks=1000,
        )
        STATE.last_stats = stats
    except Exception as e:
        logging.getLogger("app").exception("reindex failed: %s", e)
        STATE.last_error = str(e)
    finally:
        STATE.last_finished = time.time()
        STATE.running = False


@app.post("/admin/reindex")
def trigger_reindex(background: BackgroundTasks, x_token: Optional[str] = Header(None)):
    _require_token(x_token)
    if STATE.running:
        raise HTTPException(status_code=409, detail="Reindex already running")
    background.add_task(_reindex_task_sync)
    return {"status": "started"}


@app.get("/admin/reindex/status")
def reindex_status(x_token: Optional[str] = Header(None)):
    _require_token(x_token)
    return {
        "running": STATE.running,
        "last_started": STATE.last_started,
        "last_finished": STATE.last_finished,
        "last_error": STATE.last_error,
        "last_stats": STATE.last_stats,
    }
