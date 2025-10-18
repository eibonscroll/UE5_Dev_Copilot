# src/agents/elaborator_agent.py
from __future__ import annotations

import os
import time
import logging
from typing import List, Dict, Any

from pydantic import BaseModel
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser
from langchain_core.documents import Document
from langchain_openai import ChatOpenAI

log = logging.getLogger("elaborator")

# Not strictly required at runtime (retriever handles filtering),
# but kept as future heuristics you might use when biasing queries.
PLUGIN_HINT_FILES = [
    "*.uplugin",
    "README.md",
    "Readme.md",
    "readme.md",
    "Docs/*.md",
    "Source/**/*.h",
    "Source/**/*.hpp",
    "Source/**/*.cpp",
    "Source/**/*.cs",
]


class ElaboratorConfig(BaseModel):
    """Config for the elaborator agent."""
    model: str = os.getenv("OPENAI_CHAT_MODEL", "gpt-4.1-mini")
    temperature: float = float(os.getenv("OPENAI_TEMPERATURE", "0.2"))
    per_item_k: int = int(os.getenv("ELABORATOR_PER_ITEM_K", "6"))  # keep modest for speed
    timeout_s: float = float(os.getenv("ELABORATOR_TIMEOUT_S", "30"))


class ElaboratorAgent:
    """
    Takes a minimal, correct answer and a list of items (e.g., plugin names) and
    produces a richer *grounded* write-up for each item.

    Strategy:
      1) For each item, run focused retrieval queries (README / .uplugin / Source).
      2) Drop empty docs and dedupe aggressively to avoid huge prompts.
      3) Ask the LLM to summarize what the item does, citing (source: <path>).
    """

    def __init__(self, retriever, cfg: ElaboratorConfig | None = None):
        self.retriever = retriever
        self.cfg = cfg or ElaboratorConfig()
        self.llm = ChatOpenAI(
            model=self.cfg.model,
            temperature=self.cfg.temperature,
            timeout=self.cfg.timeout_s,
        )

        self.prompt = ChatPromptTemplate.from_messages([
            (
                "system",
                "You are a senior Unreal/Gameplay engineer. "
                "Write concise, *grounded* summaries from the provided context. "
                "Always include inline citations like (source: <path>). "
                "If something is unclear, say so explicitly."
            ),
            (
                "user",
                "{user_input}"
            ),
        ])
        self.chain = self.prompt | self.llm | StrOutputParser()

    # -------------------------
    # Retrieval & Query helpers
    # -------------------------
    def _focused_queries(self, item_name: str) -> List[str]:
        q = item_name.strip()
        return [
            f"{q} .uplugin purpose modules features",
            f"{q} README.md overview usage",
            f"{q} Docs markdown design architecture",
            f"{q} Source key classes functions responsibilities",
            f"{q} gameplay systems integration hooks",
        ]

    def _retrieve_for_item(self, item_name: str, per_item_k: int) -> List[Document]:
        """Retrieve docs for one item; drop empties and cap count. Logs timing."""
        t0 = time.perf_counter()
        docs_all: List[Document] = []

        for it in self._focused_queries(item_name):
            try:
                # Preferred new API
                docs = self.retriever.invoke(it)
            except Exception:
                # Fallback for older retrievers
                docs = self.retriever.get_relevant_documents(it, search_kwargs={"k": per_item_k})

            # Keep only docs that have content
            for d in docs[:per_item_k]:
                if getattr(d, "page_content", None) and d.page_content.strip():
                    docs_all.append(d)

        # Deduplicate by (first 200 chars of content + path)
        seen = set()
        deduped: List[Document] = []
        for d in docs_all:
            meta = dict(d.metadata or {})
            path = meta.get("path") or meta.get("file") or meta.get("source") or ""
            key = ((d.page_content or "")[:200], path)
            if key in seen:
                continue
            seen.add(key)
            deduped.append(d)

        # Cap total to avoid huge prompts; keep the most relevant first as returned
        deduped = deduped[: max(12, per_item_k)]

        log.info(
            "elaborator: retrieved item=%r docs=%d in %.2fs",
            item_name, len(deduped), time.perf_counter() - t0
        )
        return deduped

    # ---------------
    # Public API
    # ---------------
    def elaborate(self, base_md: str, item_label: str, items: List[str]) -> str:
        """
        Create an elaboration section for the given items.

        NOTE: This returns ONLY the elaboration section (does not prepend base_md),
        so the orchestrator can safely do: base_md + "\\n\\n" + elaboration.
        """
        if not items:
            return ""

        sections: List[str] = [f"## {item_label.title()} Details"]
        for name in items:
            d0 = time.perf_counter()
            docs = self._retrieve_for_item(name, self.cfg.per_item_k)

            if not docs:
                sections.append(f"### {name}\nNo additional context found in the index.")
                continue

            # Build numbered context; keep snippets compact
            numbered: List[str] = []
            for i, d in enumerate(docs, 1):
                meta = dict(d.metadata or {})
                path = meta.get("path") or meta.get("file") or meta.get("source") or ""
                text = (d.page_content or "").strip()
                if len(text) > 800:
                    text = text[:800] + " …"
                numbered.append(f"[{i}] {path}\n{text}")

            user_input = (
                f"ITEM: {name}\n\n"
                "CONTEXT (numbered snippets):\n" + "\n\n".join(numbered) + "\n\n"
                "Write a compact section covering:\n"
                f"- What the {item_label} does (purpose / features)\n"
                "- Notable modules/classes/functions and their brief roles\n"
                "- Integration points (e.g., systems, subsystems, menus, HUD)\n"
                "- Any configuration/INI entries or Editor modules\n"
                "Keep it grounded; add inline citations like (source: <path>)."
            )

            try:
                summary = (self.chain.invoke({"user_input": user_input}) or "").strip()
            except Exception as e:
                log.exception("elaborator: LLM failed for %r: %s", name, e)
                summary = ""

            took = time.perf_counter() - d0
            log.info("elaborator: summarized item=%r in %.2fs", name, took)

            if not summary:
                summary = "_No details available from the retrieved context._"

            sections.append(f"### {name}\n{summary}")

        return "\n\n".join(sections).rstrip()
