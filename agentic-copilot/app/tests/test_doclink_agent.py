# tests/test_doclink_agent.py
from src.agents.doclink_agent import DocLinkAgent

def test_doclink_agent_injects_links():
    agent = DocLinkAgent()
    ctxs = [
        {"path": "/ingest/plugins/HelpfulFunctions/README.md", "text": "See Unreal documentation for Gameplay Ability System"},
        {"path": "/ingest/plugins/JakubCableComponent/README.md", "text": "Documentation: https://docs.unrealengine.com/5.3/en-US/blueprints"},
    ]
    md = "HelpfulFunctions overview."
    out = agent.add_links(md, contexts=ctxs)
    # Expect at least one Unreal docs link injected (normalized)
    assert "https://docs.unrealengine.com" in out
