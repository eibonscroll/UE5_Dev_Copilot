# tests/test_orchestrator_rag.py
from src.agents.langchain_orchestrator import run_langchain_pipeline

def _fake_retrieve(query: str, k: int, top_n: int):
    return [
        {"text": "HelpfulFunctions overview", "path": "/ingest/plugins/HelpfulFunctions/README.md"},
        {"text": "JakubCableComponent overview", "path": "/ingest/plugins/JakubCableComponent/README.md"},
    ]

def test_rag_synthesis_and_elaboration(patch_llm, patch_retriever, patch_write_md):
    res = run_langchain_pipeline(
        "Explain HelpfulFunctions plugin features",
        retrieve_fn=_fake_retrieve,
        k=4,
        top_n=2,
    )
    assert res["decision"] == "YES"
    assert "Answer:" in res["markdown"]  # from DummyLLM synthesis
    assert "Summary:" in res["markdown"] # elaborator output
    assert "References" in res["markdown"]
