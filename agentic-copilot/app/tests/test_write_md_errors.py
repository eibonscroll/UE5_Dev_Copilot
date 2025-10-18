# tests/test_write_md_errors.py
from src.agents.langchain_orchestrator import _append_refs

def test_append_refs_no_crash_on_empty():
    out = _append_refs("hi", [])
    assert out.startswith("hi")
