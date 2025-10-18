# tests/conftest.py
import os
import types
import shutil
import textwrap
import pytest

# ---- Dummy LLM that returns canned markdown based on the incoming prompt text ----
class DummyLLM:
    def __init__(self, *_, **__):
        pass
    def bind_tools(self, tools):  # keep interface parity
        return self
    def __or__(self, other):
        # allow chaining like (prompt | llm | parser)
        return self
    def invoke(self, args):
        # args can be {"user_input": "..."} or prompt dict
        text = args.get("user_input", "") if isinstance(args, dict) else str(args)
        if "QUESTION:" in text and "CONTEXT:" in text:
            # RAG synthesis output
            return "Answer: **HelpfulFunctions** does X. [^1]"
        if "Write a compact section" in text:
            # Elaborator summary output
            return "Summary: purpose; notable classes; integration (source: /ingest/plugins/HelpfulFunctions/README.md)"
        # default
        return "OK"

# ---- Fake retriever that returns small in-memory “docs” ----
class FakeDoc:
    def __init__(self, page_content, metadata=None):
        self.page_content = page_content
        self.metadata = metadata or {}

class FakeRetriever:
    def __init__(self):
        self.docs = [
            FakeDoc("HelpfulFunctions overview", {"path": "/ingest/plugins/HelpfulFunctions/README.md"}),
            FakeDoc("JakubCableComponent overview", {"path": "/ingest/plugins/JakubCableComponent/README.md"}),
        ]
    def get_relevant_documents(self, query, search_kwargs=None):
        k = (search_kwargs or {}).get("k", 8)
        return self.docs[:k]
    # newer API used by some code paths
    def invoke(self, query):
        return self.get_relevant_documents(query, {"k": 8})

@pytest.fixture(autouse=True)
def clean_env(tmp_path, monkeypatch):
    # keep outputs isolated per test
    monkeypatch.setenv("OPENAI_CHAT_MODEL", "dummy-model")
    monkeypatch.setenv("OPENAI_TEMPERATURE", "0.0")
    monkeypatch.setenv("ELABORATOR_PER_ITEM_K", "4")
    # force out dir to tmp
    monkeypatch.setenv("OUT_DIR_FOR_TESTS", str(tmp_path))
    yield
    # cleanup
    shutil.rmtree(tmp_path, ignore_errors=True)

@pytest.fixture
def patch_llm(monkeypatch):
    # Patch ChatOpenAI used across orchestrator/elaborator
    import src.agents.langchain_orchestrator as orch
    import src.agents.elaborator_agent as elab
    def _llm(*args, **kwargs):
        return DummyLLM()
    monkeypatch.setattr(orch, "_llm", _llm, raising=True)
    monkeypatch.setattr(elab, "ChatOpenAI", lambda *a, **k: DummyLLM(), raising=True)

@pytest.fixture
def patch_retriever(monkeypatch):
    import src.agents.langchain_orchestrator as orch
    fr = FakeRetriever()
    monkeypatch.setattr(orch, "_get_retriever", lambda: fr, raising=True)
    return fr

@pytest.fixture
def patch_write_md(monkeypatch, tmp_path):
    # Route _write_md to tmp dir from env
    import src.agents.langchain_orchestrator as orch
    def _write_md(markdown: str, out_dir: str = None, stem: str = "") -> str:
        out_dir = out_dir or os.getenv("OUT_DIR_FOR_TESTS", str(tmp_path))
        os.makedirs(out_dir, exist_ok=True)
        if not markdown.strip():
            return ""
        p = os.path.join(out_dir, f"{stem or 'answer'}.md")
        with open(p, "w", encoding="utf-8") as f:
            f.write(markdown)
        return p
    monkeypatch.setattr(orch, "_write_md", _write_md, raising=True)

@pytest.fixture
def minimal_contexts():
    return [
        {"text": "HelpfulFunctions overview", "path": "/ingest/plugins/HelpfulFunctions/README.md"},
        {"text": "Other context", "path": "/ingest/plugins/HelpfulFunctions/Source/X.cpp"},
    ]
