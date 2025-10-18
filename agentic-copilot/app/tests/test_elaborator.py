# tests/test_elaborator.py
from src.agents.elaborator_agent import ElaboratorAgent, ElaboratorConfig

def test_elaborator_sections(patch_llm, patch_retriever):
    cfg = ElaboratorConfig(model="dummy", temperature=0.0, per_item_k=4)
    agent = ElaboratorAgent(retriever=patch_retriever, cfg=cfg)
    base = "Plugins found:\n- HelpfulFunctions"
    md = agent.elaborate(base, item_label="plugin", items=["HelpfulFunctions"])
    assert "## Plugin Details" in md
    assert "### HelpfulFunctions" in md
    assert "Summary:" in md
