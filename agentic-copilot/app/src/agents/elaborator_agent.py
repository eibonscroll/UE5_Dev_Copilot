# src/agents/elaborator_agent.py
from __future__ import annotations
import os
from typing import List, Dict, Any
from pydantic import BaseModel
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser
from langchain_openai import ChatOpenAI

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
    model: str = os.getenv("OPENAI_CHAT_MODEL", "gpt-4.1-mini")
    temperature: float = float(os.getenv("OPENAI_TEMPERATURE", "0.2"))
    # how many docs to pull per item (plugin/module/etc.)
    per_item_k: int = int(os.getenv("ELABORATOR_PER_ITEM_K", "8"))

class ElaboratorAgent:
    """
    Takes the base answer and list of items (e.g., plugin names) and produces a
    richer write-up grounded in repository content.

    Strategy:
      1) For each item, issue several focused retrievals that bias toward:
         - *.uplugin files
         - README/Docs markdown
         - Source/**/*.h, **/*.cpp, **/*.cs
      2) Summarize purpose + key modules + notable classes/functions + where used.
      3) Output concise sections with citations “(source: <path>)”.
    """
    def __init__(self, retriever, cfg: ElaboratorConfig | None = None):
        self.retriever = retriever
        self.cfg = cfg or ElaboratorConfig()
        self.llm = ChatOpenAI(model=self.cfg.model, temperature=self.cfg.temperature)

        self.prompt = ChatPromptTemplate.from_messages([
            ("system",
             "You are a senior Unreal/Gameplay engineer. "
             "Write concise, *grounded* summaries from the provided context. "
             "Always include inline citations like (source: <path>). "
             "If something is unclear, say so explicitly."),
            ("user", "{user_input}")
        ])
        self.chain = self.prompt | self.llm | StrOutputParser()

    def _focused_queries(self, item_name: str) -> List[str]:
        # Nudge retrieval toward the files that actually describe a plugin/module.
        q = item_name.strip()
        return [
            f"{q} .uplugin purpose modules features",
            f"{q} README.md overview usage",
            f"{q} Docs markdown design architecture",
            f"{q} Source key classes functions responsibilities",
            f"{q} gameplay systems integration hooks",
        ]

    def _retrieve_for_item(self, item_name: str, per_item_k: int) -> List[Dict[str, Any]]:
        """Return a list of dicts: [{page_content, path}]"""
        results: List[Dict[str, Any]] = []
        for it in self._focused_queries(item_name):
            # LangChain deprecates get_relevant_documents soon; invoke() is fine,
            # but many retrievers still support the method. Keep both behaviors safe.
            try:
                docs = self.retriever.invoke(it)  # Preferred new API
            except Exception:
                docs = self.retriever.get_relevant_documents(it, search_kwargs={"k": per_item_k})  # fallback

            for d in docs[:per_item_k]:
                meta = dict(d.metadata or {})
                results.append({
                    "page_content": d.page_content or "",
                    "path": meta.get("path") or meta.get("file") or meta.get("source") or "",
                })
        # Dedup by (content,path) to keep context short-ish
        seen = set()
        deduped = []
        for r in results:
            key = (r["page_content"][:200], r["path"])
            if key in seen:
                continue
            seen.add(key)
            deduped.append(r)
        return deduped[: max(12, per_item_k)]  # cap a bit; avoid huge prompts

    def elaborate(self, base_md: str, item_label: str, items: List[str]) -> str:
        """
        base_md: the already-correct minimal answer we produced.
        item_label: singular label for items, e.g. 'plugin' or 'module'
        items: list of names to elaborate on (e.g., plugin names)
        """
        sections = [base_md.rstrip(), "\n---\n", f"## {item_label.title()} Details\n"]
        for name in items:
            ctx = self._retrieve_for_item(name, self.cfg.per_item_k)
            if not ctx:
                sections.append(f"### {name}\nCouldn’t find any descriptive files for this {item_label}.")
                continue

            numbered = []
            for i, r in enumerate(ctx, 1):
                text = (r["page_content"] or "").strip()
                if len(text) > 1000:
                    text = text[:1000] + " …"
                path = r.get("path", "")
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

            summary = (self.chain.invoke({"user_input": user_input}) or "").strip()
            if not summary:
                summary = f"Could not generate a summary for {name}."

            sections.append(f"### {name}\n{summary}\n")

        return "\n".join(sections).rstrip()
