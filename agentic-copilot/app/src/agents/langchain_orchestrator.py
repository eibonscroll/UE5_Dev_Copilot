from __future__ import annotations
# src/agents/langchain_orchestrator.py
import functools
import re
import os, logging, time, hashlib, pathlib
from typing import List, Dict, Any, Callable

from pydantic import BaseModel
from src.settings import SETTINGS

# LangChain core
from langchain_core.tools import tool
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.output_parsers import StrOutputParser

# LLM
from langchain_openai import ChatOpenAI

# Vector / embeddings
from langchain_community.vectorstores import Qdrant as LCQdrant
from langchain_community.embeddings import HuggingFaceEmbeddings
from qdrant_client import QdrantClient

# Existing Inventory agent
from src.agents.inventory_agent import run as run_inventory_agent
from src.agents.doclink_agent import DocLinkAgent
# NEW: ElaboratorAgent
from src.agents.elaborator_agent import ElaboratorAgent, ElaboratorConfig

# --- Keep a single retriever instance in memory ---
_RETRIEVER: Any = None

log = logging.getLogger("orchestrator")


# ---------- helpers ----------
def _write_md(markdown: str, out_dir: str = "/app/out", stem: str = "") -> str:
    os.makedirs(out_dir, exist_ok=True)
    if not markdown or not markdown.strip():
        return ""
    run_id = stem or hashlib.sha1(str(time.time()).encode()).hexdigest()[:8]
    path = os.path.join(out_dir, f"answer-{run_id}.md")
    with open(path, "w", encoding="utf-8") as f:
        f.write(markdown)
    return path


def _make_prompt(query: str, refs: List[Dict[str, Any]]) -> str:
    numbered = []
    for i, r in enumerate(refs, 1):
        text = (r.get("text") or "")[:1200]
        path = r.get("path") or r.get("file") or ""
        numbered.append(f"[{i}] {path}\n{text}")
    return (
        "You are a senior Unreal/Gameplay engineer assistant.\n"
        "Answer ONLY using the numbered CONTEXT. Use citations like [^n]. "
        "If info is missing, say what is missing.\n\n"
        f"QUESTION:\n{query}\n\n"
        "CONTEXT:\n" + "\n\n".join(numbered)
    )


def _llm(model_env="OPENAI_CHAT_MODEL", temp_env="OPENAI_TEMPERATURE", default_model="gpt-4.1-mini", default_temp=0.2):
    model = os.getenv(model_env, default_model)
    temperature = float(os.getenv(temp_env, str(default_temp)))
    return ChatOpenAI(model=model, temperature=temperature, timeout=60)


def generate_answer(query: str, contexts: List[Dict[str, Any]]) -> str:
    llm = _llm()
    prompt = ChatPromptTemplate.from_messages([
        ("system", "Return clean, concise Markdown. Include citations [^n]."),
        ("user", "{user_input}"),
    ])
    chain = prompt | llm | StrOutputParser()
    user_input = _make_prompt(query, contexts)
    md = chain.invoke({"user_input": user_input}) or ""
    return md.strip()


# ---------- retriever ----------
def _embedding_fn(model_name: str):
    # Keep it consistent with your index (BAAI/bge-small-en, dim=384)
    # NOTE: you can switch to langchain-huggingface later; this works now.
    return HuggingFaceEmbeddings(
        model_name=model_name,
        encode_kwargs={"normalize_embeddings": True},
    )

def _build_retriever() -> Any:
    emb = _embedding_fn(SETTINGS.embedding_model)
    client = QdrantClient(
        url=SETTINGS.qdrant_url,
        prefer_grpc=True,
        grpc_port=6334,
        timeout=30.0,  # lower than before so failures don’t feel like a hang
    )
    vs = LCQdrant(
        client=client,
        collection_name=SETTINGS.collection,
        embeddings=emb,
        content_payload_key="text",        # IMPORTANT: your payload uses "text"
        metadata_payload_key=None,
    )
    return vs.as_retriever(search_kwargs={"k": 8})

def _get_retriever() -> Any:
    global _RETRIEVER
    if _RETRIEVER is None:
        log.info("retriever: building (cold start)")
        _RETRIEVER = _build_retriever()
        log.info("retriever: ready")
    return _RETRIEVER

# ---------- tools ----------
class SearchArgs(BaseModel):
    query: str
    k: int = 8

@tool("search_docs", args_schema=SearchArgs)
def search_docs(query: str, k: int = 8) -> List[Dict[str, Any]]:
    """
    Search the indexed Unreal docs/code in Qdrant and return the top-k results.
    Always call this before answering. Each result includes:
      - page_content: the text chunk
      - path/source: a path or module/file hint you can cite in the answer
    """
    retriever = _get_retriever()
    docs = retriever.get_relevant_documents(query, search_kwargs={"k": k})
    out = []
    for d in docs:
        meta = dict(d.metadata or {})
        out.append({
            "page_content": d.page_content,
            "source": meta.get("source") or meta.get("file") or meta.get("path"),
            "path": meta.get("path") or meta.get("file"),
        })
    return out

class MermaidArgs(BaseModel):
    spec: str

@tool("make_mermaid", args_schema=MermaidArgs)
def make_mermaid(spec: str) -> str:
    """
    Validate and wrap a Mermaid diagram spec in a fenced code block.
    Pass only the inner Mermaid definition (no backticks).
    Returns a Markdown string containing a ```mermaid fenced block.
    """
    spec = spec.strip()
    if not spec:
        return "No diagram content."
    if len(spec) > 8000:
        spec = spec[:8000] + "\n\n%% truncated"
    return f"```mermaid\n{spec}\n```"

# ---------- agent graph ----------
SYSTEM = """You are a helpful Unreal Engine code/doc assistant.
CRITICAL RULES:
- Ground your answers ONLY on retrieved context from the `search_docs` tool.
- Always cite snippets inline like: (source: <path or source>).
- If information is missing, say so and suggest a file/path to inspect.
- If the user asks for a diagram, call `make_mermaid` and include its output verbatim.
- Prefer concise, stepwise, actionable answers; include filenames and symbols when relevant.
"""

def _llm_or_none():
    if SETTINGS.has_openai_key:
        return _llm(default_temp=0.1)
    return None

def _agent_graph():
    llm = _llm_or_none()
    tools = [search_docs, make_mermaid]
    if llm is not None:
        llm = llm.bind_tools(tools)
        prompt = ChatPromptTemplate.from_messages(
            [("system", SYSTEM), MessagesPlaceholder("messages")]
        )
        chain = prompt | llm
        return chain, tools

    # no-LLM fallback (unused in current flow but kept for completeness)
    def fallback_run(query: str) -> str:
        hits = search_docs.invoke({"query": query, "k": 8})  # type: ignore
        if not hits:
            return "I couldn't find anything relevant in the index for that query."
        md = ["### Answer (no LLM mode)\n", "_Top matches:_\n"]
        for h in hits[:8]:
            src = h.get("path") or h.get("source") or "unknown"
            md.append(f"- ({src})")
        return "\n".join(md)
    return fallback_run, tools


# ---------- intent ----------
def _detect_intent(q: str) -> str:
    """
    Return 'list_plugins' only for queries clearly asking for the names of plugins.
    Otherwise, fall back to 'rag'.
    """
    ql = q.lower().strip()

    # Heuristics that *really* look like "what are the plugin names"
    plugin_names_patterns = [
        r"\bnames?\s+of\s+the\s+plugins?\b",
        r"\bwhat\s+are\s+the\s+plugins?\b",
        r"\bwhich\s+plugins?\b",
        r"\blist\s+the\s+plugins?\b",
        r"\bplugins?\s+list\b",
    ]
    if any(re.search(p, ql) for p in plugin_names_patterns):
        return "list_plugins"

    # If the query is about *a specific* plugin/module/content, stay in RAG.
    # Examples that should NOT trigger list_plugins:
    # "list the functions in the plugin HelpfulFunctions"
    # "what does the HelpfulFunctions plugin do"
    # "show me modules in JakubAnimNodes"
    return "rag"

# ---------- public orchestrator ----------
def _append_refs(md: str, ctxs: List[Dict[str, Any]]) -> str:
    refs = "\n".join([f"[^{i}] {c.get('path') or c.get('file') or ''}"
                      for i, c in enumerate(ctxs, 1)])
    return md + ("\n\n---\n**References**\n\n" + refs if refs.strip() else "")

# --- Model selection & quality gate ---
def _llm_with(model: str, temperature: float | None = None):
    t = float(os.getenv("OPENAI_TEMPERATURE", "0.2")) if temperature is None else temperature
    return ChatOpenAI(model=model, temperature=t, timeout=60)

def _needs_escalation(md: str, expect_citations: bool = True) -> bool:
    if not md or len(md.strip()) < int(os.getenv("ESCALATE_MIN_CHARS", "280")):
        return True
    if expect_citations and "[^" not in md:
        return True
    return False

def _synthesize_with_escalation(query: str, contexts: List[Dict[str, Any]]) -> str:
    """Try fast model first; if weak, retry once with stronger model."""
    fast_model = os.getenv("OPENAI_CHAT_MODEL", "gpt-4.1-mini")
    strong_model = os.getenv("OPENAI_STRONG_MODEL", "gpt-4.1")  # set via env to control
    expect_cites = True

    def _make_chain(llm):
        prompt = ChatPromptTemplate.from_messages([
            ("system", "Return clean, concise Markdown. Include citations [^n]."),
            ("user", "{user_input}"),
        ])
        return prompt | llm | StrOutputParser()

    # first pass (fast)
    md = (_make_chain(_llm_with(fast_model))
          .invoke({"user_input": _make_prompt(query, contexts)}) or "").strip()
    if not _needs_escalation(md, expect_cites):
        return md

    # second pass (strong)
    md2 = (_make_chain(_llm_with(strong_model))
           .invoke({"user_input": _make_prompt(query, contexts)}) or "").strip()
    return md2 or md  # fall back to first if second somehow empty


def run_langchain_pipeline(
    query: str,
    retrieve_fn: Callable[[str, int, int], List[Dict[str, Any]]],
    k: int = 60,
    top_n: int = 8,
) -> Dict[str, Any]:
    """
    Pipeline:
      - Intent detect (+ InventoryAgent for list-style intents)
      - RAG (retrieve_fn -> synthesize)
      - ElaboratorAgent for grounded “what these do”
    """
    t0 = time.perf_counter()
    run_id = hashlib.sha1(f"{time.time()}-{query}".encode()).hexdigest()[:8]

    try:
        intent = _detect_intent(query)
        log.info("orchestrator: intent=%s run_id=%s", intent, run_id)

        # -------------------------------
        # Helper: extract items to expand
        # -------------------------------
        def _extract_items_from_markdown(md: str) -> list[str]:
            items: list[str] = []
            for line in (md or "").splitlines():
                if line.strip().startswith(("-", "*", "•")):
                    name = line.lstrip("-*• \t").strip()
                    # keep short/simple names only (single token plugin/module names)
                    if 2 <= len(name) <= 64 and " " not in name:
                        items.append(name)
            # de-dup preserving order
            return list(dict.fromkeys(items))

        def _extract_items_from_contexts(ctxs: List[Dict[str, Any]]) -> list[str]:
            # fall back to plugin folder names under /plugins/<NAME>/...
            possible: list[str] = []
            for c in ctxs:
                p = (c.get("path") or c.get("file") or "") or ""
                if "/plugins/" in p:
                    try:
                        parts = p.split("/plugins/")[1].split("/")
                        if parts and parts[0]:
                            possible.append(parts[0])
                    except Exception:
                        pass
            return list(dict.fromkeys(possible))

        # --------------------------------
        # Inventory route (list_plugins)
        # --------------------------------
        if intent == "list_plugins":
            inv = run_inventory_agent(query)
            base_md = inv.get("markdown", "") or "_No plugins found._"

            # detect items for elaboration
            items = _extract_items_from_markdown(base_md)
            if not items:
                # try a direct scan using retriever too (optional)
                retriever = _get_retriever()
                # probe some results to harvest names from paths
                docs = retriever.get_relevant_documents("list of plugins", search_kwargs={"k": 12})
                for d in docs:
                    p = (d.metadata or {}).get("path") or (d.metadata or {}).get("file") or ""
                    if "/plugins/" in p:
                        try:
                            parts = p.split("/plugins/")[1].split("/")
                            if parts and parts[0]:
                                items.append(parts[0])
                        except Exception:
                            pass
                items = list(dict.fromkeys(items))

            # Elaborate (plugins)
            try:
                retriever = _get_retriever()
                from src.agents.elaborator_agent import ElaboratorAgent, ElaboratorConfig
                elab_cfg = ElaboratorConfig(
                    model=os.getenv("OPENAI_CHAT_MODEL", "gpt-4.1-mini"),
                    temperature=float(os.getenv("OPENAI_TEMPERATURE", "0.2")),
                    per_item_k=int(os.getenv("ELABORATOR_PER_ITEM_K", "8")),
                )
                elaborator = ElaboratorAgent(retriever=retriever, cfg=elab_cfg)
                if items:
                    elaboration = elaborator.elaborate(base_md, item_label="plugin", items=items)
                else:
                    elaboration = ""

                md_out = base_md + ("\n\n" + elaboration if elaboration else "")
            except Exception as e:
                log.exception("elaborator failed (inventory): %s", e)
                md_out = base_md + "\n\n> _(Elaboration step failed; base answer shown.)_"

            ##append any official Unreal docs URLs found in retrieved snippets
            md_out = DocLinkAgent().add_links(md_out, contexts=[])

            fs_path = _write_md(md_out, stem=f"answer-{run_id}")
            file_url = f"/download/{os.path.basename(fs_path)}" if fs_path else ""
            log.info("orchestrator: inventory ok run_id=%s duration=%.3fs",
                     run_id, time.perf_counter() - t0)
            return {"decision": "YES", "markdown": md_out, "file": file_url}

        # ----------------
        # Default RAG flow
        # ----------------
        ctxs = retrieve_fn(query, k=k, top_n=top_n)
        if not ctxs:
            md = "_No relevant results._"
            fs_path = _write_md(md, stem=f"answer-{run_id}")
            file_url = f"/download/{os.path.basename(fs_path)}" if fs_path else ""
            return {"decision": "YES", "markdown": md, "file": file_url}

        base_md = _synthesize_with_escalation(query, ctxs)
        if not base_md:
            log.warning("Empty LLM output for query=%r", query)
            return {"decision": "NO", "message": "LLM returned empty response.", "markdown": "", "file": ""}

        # ---- Elaborate based on items detected ----
        items = _extract_items_from_markdown(base_md)
        if not items:
            items = _extract_items_from_contexts(ctxs)

        try:
            retriever = _get_retriever()
            from src.agents.elaborator_agent import ElaboratorAgent, ElaboratorConfig
            elab_cfg = ElaboratorConfig(
                model=os.getenv("OPENAI_CHAT_MODEL", "gpt-4.1-mini"),
                temperature=float(os.getenv("OPENAI_TEMPERATURE", "0.2")),
                per_item_k=int(os.getenv("ELABORATOR_PER_ITEM_K", "8")),
            )
            elaborator = ElaboratorAgent(retriever=retriever, cfg=elab_cfg)

            lower_q = query.lower()
            item_label = "plugin" if "plugin" in lower_q else ("module" if "module" in lower_q else "item")
            if items:
                elaboration = elaborator.elaborate(base_md, item_label=item_label, items=items)
            else:
                elaboration = ""
            md_out = base_md + ("\n\n" + elaboration if elaboration else "")
        except Exception as e:
            log.exception("elaborator failed (rag): %s", e)
            md_out = base_md + "\n\n> _(Elaboration step failed; base answer shown.)_"

        # Append references & write file
        md_out = _append_refs(md_out, ctxs)

        #append any official Unreal docs URLs found in retrieved snippets
        md_out = DocLinkAgent().add_links(md_out, contexts=ctxs)

        fs_path = _write_md(md_out, stem=f"answer-{run_id}")
        file_url = f"/download/{os.path.basename(fs_path)}" if fs_path else ""

        log.info(
            "orchestrator: ok run_id=%s duration=%.3fs",
            os.path.basename(fs_path).replace(".md", "") if fs_path else "-",
            time.perf_counter() - t0,
        )
        return {"decision": "YES", "markdown": md_out, "file": file_url}

    except Exception as e:
        log.exception("orchestrator: failed run_id=%s: %s", run_id, e)
        return {"decision": "NO", "message": str(e)}
