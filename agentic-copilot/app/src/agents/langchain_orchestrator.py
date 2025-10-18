# src/agents/langchain_orchestrator.py
from __future__ import annotations
import os, logging, time, hashlib, uuid, pathlib
from typing import List, Dict, Any, Callable

from pydantic import BaseModel
from src.settings import SETTINGS

# --- LangChain core ---
from langchain_core.tools import tool
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.runnables import RunnableConfig
from langchain_core.output_parsers import StrOutputParser

# --- LLM (optional) ---
from langchain_openai import ChatOpenAI

# --- Vector store / embeddings ---
from langchain_community.vectorstores import Qdrant as LCQdrant
from langchain_community.embeddings import HuggingFaceEmbeddings
from qdrant_client import QdrantClient

# --- New: Inventory agent (filesystem-based) ---
from src.agents.inventory_agent import run as run_inventory_agent  # <- add this file if not present

log = logging.getLogger("orchestrator")


# --------------------
# File helpers
# --------------------
def _write_md(markdown: str, out_dir: str = "/app/out", stem: str = "") -> str:
    """
    Writes markdown to /app/out/answer-<stem or runid>.md (if non-empty) and
    returns the FILESYSTEM path. Callers can convert to /download/<name>.
    """
    os.makedirs(out_dir, exist_ok=True)
    if not markdown or not markdown.strip():
        return ""  # don't write empty files
    run_id = stem or hashlib.sha1(str(time.time()).encode()).hexdigest()[:8]
    path = os.path.join(out_dir, f"answer-{run_id}.md")
    with open(path, "w", encoding="utf-8") as f:
        f.write(markdown)
    return path


# --------------------
# Prompting / LLM glue
# --------------------
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


def generate_answer(query: str, contexts: List[Dict[str, Any]]) -> str:
    """Return a plain markdown string (never None)."""
    model = os.getenv("OPENAI_CHAT_MODEL", "gpt-4.1-mini")
    temperature = float(os.getenv("OPENAI_TEMPERATURE", "0.2"))

    llm = ChatOpenAI(model=model, temperature=temperature)
    prompt = ChatPromptTemplate.from_messages([
        ("system", "Return clean, concise Markdown. Include citations [^n]."),
        ("user", "{user_input}"),
    ])
    chain = prompt | llm | StrOutputParser()  # <- guarantees a str

    user_input = _make_prompt(query, contexts)
    md = chain.invoke({"user_input": user_input}) or ""
    return md.strip()


# ----------------------------
# Embeddings + Retriever glue
# ----------------------------
def _embedding_fn(model_name: str):
    # Keep it consistent with your index (BAAI/bge-small-en, dim=384)
    return HuggingFaceEmbeddings(model_name=model_name, encode_kwargs={"normalize_embeddings": True})


def _make_retriever() -> Any:
    emb = _embedding_fn(SETTINGS.embedding_model)
    client = QdrantClient(url=SETTINGS.qdrant_url, prefer_grpc=True, grpc_port=6334, timeout=60.0)
    vs = LCQdrant(
        client=client,
        collection_name=SETTINGS.collection,
        embeddings=emb,
    )
    # k is adjusted at call-time; here provide a sane default
    retriever = vs.as_retriever(search_kwargs={"k": 8})
    return retriever


# --------------------------------
# Tools the agent can call
# --------------------------------
class SearchArgs(BaseModel):
    query: str
    k: int = 8


@tool("search_docs", args_schema=SearchArgs)
def search_docs(query: str, k: int = 8) -> List[Dict[str, Any]]:
    """
    Search the indexed docs/code in Qdrant and return the top-k results.
    ALWAYS call this before answering. Cite the 'source' and 'path' in the answer.
    """
    retriever = _make_retriever()
    docs = retriever.get_relevant_documents(query, search_kwargs={"k": k})
    out = []
    for d in docs:
        # d.metadata may contain path/source; your index used 'file','path','source','text'
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
    Validate and return a Mermaid diagram block. Pass only the inner mermaid spec (no backticks).
    """
    spec = spec.strip()
    if not spec:
        return "No diagram content."
    # Minimal guard: cap length
    if len(spec) > 8000:
        spec = spec[:8000] + "\n%% truncated"
    return f"```mermaid\n{spec}\n```"


# --------------------------------
# System prompt for the agent
# --------------------------------
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
        # Default to small fast model; user can override via env OPENAI_CHAT_MODEL
        model = os.getenv("OPENAI_CHAT_MODEL", "gpt-4.1-mini")
        temperature = float(os.getenv("OPENAI_TEMPERATURE", "0.1"))
        return ChatOpenAI(model=model, temperature=temperature, timeout=60)
    return None


def _agent_graph():
    """Return either a tool-calling LLM agent or a simple retrieval chain fallback."""
    llm = _llm_or_none()
    tools = [search_docs, make_mermaid]

    if llm is not None:
        llm = llm.bind_tools(tools)

        prompt = ChatPromptTemplate.from_messages(
            [
                ("system", SYSTEM),
                MessagesPlaceholder("messages"),  # we'll inject [("human", query)]
            ]
        )
        chain = prompt | llm
        return chain, tools

    # ------- No-LLM fallback (still grounded & useful) -------
    def fallback_run(query: str) -> str:
        hits = search_docs.invoke({"query": query, "k": 8})  # type: ignore
        if not hits:
            return "I couldn't find anything relevant in the index for that query."
        md = ["### Answer (no LLM mode)\n"]
        md.append("_Top matches:_\n")
        for h in hits[:8]:
            src = h.get("path") or h.get("source") or "unknown"
            md.append(f"- ({src})")
        md.append("\n---\n")
        md.append("**Context excerpts:**\n")
        for h in hits[:6]:
            src = h.get("path") or h.get("source") or "unknown"
            snippet = (h["page_content"] or "").strip()
            if len(snippet) > 600:
                snippet = snippet[:600] + " …"
            md.append(f"**{src}**\n\n> {snippet}\n")
        return "\n".join(md)

    return fallback_run, tools


# --------------------------------
# Intent detection + routing
# --------------------------------
def _detect_intent(q: str) -> str:
    ql = q.lower()
    if "plugin" in ql and any(w in ql for w in ["name", "names", "list", "what are", "which"]):
        return "list_plugins"
    return "rag"  # default: generic RAG answer


# --------------------------------
# Public entrypoint
# --------------------------------
def run_langchain_pipeline(
    query: str,
    retrieve_fn: Callable[[str, int, int], List[Dict[str, Any]]],
    k: int = 60,
    top_n: int = 8,
) -> Dict[str, Any]:
    """
    Orchestrates multiple agents:
      - InventoryAgent for inventory questions (e.g., 'list plugins')
      - RAG Agent (your existing retrieve -> synthesize -> package)
    """
    t0 = time.perf_counter()
    run_id = hashlib.sha1(f"{time.time()}-{query}".encode()).hexdigest()[:8]

    try:
        intent = _detect_intent(query)
        log.info("orchestrator: intent=%s run_id=%s", intent, run_id)

        # ---------- Inventory route ----------
        if intent == "list_plugins":
            inv = run_inventory_agent(query)
            md = inv.get("markdown", "") or "_No plugins found._"
            # Package and return a downloadable URL
            fs_path = _write_md(md, stem=f"answer-{run_id}")
            file_url = f"/download/{os.path.basename(fs_path)}" if fs_path else ""
            inv["file"] = file_url
            log.info("orchestrator: inventory ok run_id=%s duration=%.3fs",
                     run_id, time.perf_counter() - t0)
            return inv

        # ---------- Default RAG route ----------
        ctxs = retrieve_fn(query, k=k, top_n=top_n)  # your adapter maps VDB hits -> {path,text,score}
        if not ctxs:
            md = "_No relevant results._"
            fs_path = _write_md(md, stem=f"answer-{run_id}")
            file_url = f"/download/{os.path.basename(fs_path)}" if fs_path else ""
            return {"decision": "YES", "markdown": md, "file": file_url}

        md = generate_answer(query, ctxs)
        if not md:
            log.warning("Empty LLM output for query=%r", query)
            return {
                "decision": "NO",
                "message": "LLM returned an empty response. Try rephrasing or check logs.",
                "markdown": "",
                "file": ""
            }

        # Append simple references section
        refs = "\n".join([f"[^{i}] {c.get('path') or c.get('file') or ''}"
                          for i, c in enumerate(ctxs, 1)])
        md_out = md + ("\n\n---\n**References**\n\n" + refs if refs.strip() else "")

        fs_path = _write_md(md_out, stem=f"answer-{run_id}")
        file_url = f"/download/{os.path.basename(fs_path)}" if fs_path else ""

        dt = time.perf_counter() - t0
        log.info("orchestrator: ok run_id=%s duration=%.3fs", os.path.basename(fs_path).replace(".md","") if fs_path else "-", dt)

        return {"decision": "YES", "markdown": md_out, "file": file_url}

    except Exception as e:
        log.exception("orchestrator: failed run_id=%s: %s", run_id, e)
        return {"decision": "NO", "message": str(e)}
