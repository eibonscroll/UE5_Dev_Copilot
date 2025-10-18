# tests/test_orchestrator_inventory.py
from src.agents.langchain_orchestrator import run_langchain_pipeline

def _fake_retrieve(query: str, k: int, top_n: int):
    # not used on list intent, but keep signature
    return []

def test_inventory_list_and_elaborate(patch_llm, patch_retriever, patch_write_md):
    # This query should route to the inventory agent
    res = run_langchain_pipeline("What are the names of the 6 plugins?", _fake_retrieve)
    assert res["decision"] == "YES"
    assert "Plugins" in res["markdown"]
    # elaboration section from DummyLLM
    assert "Details" in res["markdown"]
    assert res["file"]
