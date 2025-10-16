# src/agents/rag_query.py
from __future__ import annotations
from typing import Any, Dict, List
import logging
from ..rerank import CrossEncoderReranker

log = logging.getLogger("rag")
_reranker = CrossEncoderReranker()  # lazy-loaded on first use

def _payload_of(hit: Any) -> Dict[str, Any]:
    if isinstance(hit, dict):
        return hit.get("payload", {}) or {}
    return getattr(hit, "payload", {}) or {}

def _score_of(hit: Any) -> float:
    if isinstance(hit, dict):
        return float(hit.get("score", 0.0) or 0.0)
    return float(getattr(hit, "score", 0.0) or 0.0)

def handle(query: str, embedder, vdb, k: int = 50) -> Dict[str, Any]:
    """
    1) Embed query
    2) Vector search (k=50)
    3) Cross-encoder rerank to top 8
    4) Return normalized data ready for UI/markdown
    """
    qvec = embedder.embed([query])[0]
    hits = vdb.search(qvec, k=k, with_payload=True, with_vectors=False)

    # Normalize initial hits
    norm = []
    for h in hits:
        p = _payload_of(h)
        path = p.get("path") or p.get("file") or ""
        source = p.get("source") or ""
        text = p.get("text") or ""
        _id = h.get("id") if isinstance(h, dict) else getattr(h, "id", None)
        norm.append({"id": _id, "score": _score_of(h), "payload": {"path": path, "source": source, "text": text}})

    log.info("rag: vector hits=%d (top cos=%.3f)", len(norm), norm[0]["score"] if norm else -1.0)

    # Rerank with cross-encoder
    reranked = _reranker.rerank(query, norm, top_n=8)
    log.info("rag: reranked to %d", len(reranked))

    # Build concise snippets for UI/markdown
    results = []
    for h in reranked:
        p = h["payload"]
        txt = p["text"].replace("\r", " ").replace("\n", " ")
        snippet = (txt[:320] + "…") if len(txt) > 320 else txt
        results.append({
            "path": p["path"],
            "source": p["source"],
            "snippet": snippet,
            "score": h["score"],
            "rerank": h.get("rerank_score"),
        })

    return {
        "query": query,
        "results": results,
    }
