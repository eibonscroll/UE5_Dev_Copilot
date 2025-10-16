# src/rerank.py
from __future__ import annotations
import logging
from typing import List, Dict, Any, Tuple

log = logging.getLogger("rerank")

class CrossEncoderReranker:
    """
    Lazy-loads a small cross-encoder for reranking retrieval hits by relevance.
    Model: cross-encoder/ms-marco-MiniLM-L-6-v2  (~120MB)
    """
    def __init__(self, model_name: str = "cross-encoder/ms-marco-MiniLM-L-6-v2"):
        self.model_name = model_name
        self._model = None

    @property
    def model(self):
        if self._model is None:
            from sentence_transformers import CrossEncoder
            log.info("rerank: loading cross-encoder %s", self.model_name)
            self._model = CrossEncoder(self.model_name)
        return self._model

    def rerank(self, query: str, hits: List[Dict[str, Any]], top_n: int = 8) -> List[Dict[str, Any]]:
        if not hits:
            return []

        pairs: List[Tuple[str, str]] = []
        texts: List[str] = []
        for h in hits:
            p = h.get("payload") or {}
            t = p.get("text") or ""
            if not t:
                continue
            pairs.append((query, t))
            texts.append(t)

        if not pairs:
            return hits[:top_n]

        scores = self.model.predict(pairs)  # higher = better
        scored = []
        j = 0
        for h in hits:
            p = h.get("payload") or {}
            if p.get("text"):
                scored.append((float(scores[j]), h))
                j += 1
        scored.sort(key=lambda x: x[0], reverse=True)

        out: List[Dict[str, Any]] = []
        for s, h in scored[:top_n]:
            hh = dict(h)
            hh["rerank_score"] = float(s)
            out.append(hh)
        return out
