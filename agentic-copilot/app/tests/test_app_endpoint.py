# tests/test_app_endpoint.py
import json
from fastapi.testclient import TestClient
from src.main import app

def test_health_root():
    c = TestClient(app)
    r = c.get("/")
    assert r.status_code in (200, 404, 302)  # depending on your root handler

def test_ask_endpoint_offline(monkeypatch):
    # short-circuit orchestrator with a canned response
    from src import main as m

    def fake_pipeline(prompt):
        return {"decision": "YES", "markdown": f"Echo: {prompt}", "file": ""}

    monkeypatch.setattr(m, "run_langchain_pipeline", lambda p: fake_pipeline(p), raising=True)

    c = TestClient(m.app)
    r = c.post("/ask", json={"prompt": "hello"})
    assert r.status_code == 200
    body = r.json()
    assert body["decision"] == "YES"
    assert "Echo:" in body["markdown"]
