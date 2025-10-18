# tests/test_integration_smoke.py
import os
import pytest
import requests

pytestmark = pytest.mark.skipif(
    not os.environ.get("INTEG"),
    reason="set INTEG=1 to run integration smoke tests against running docker stack",
)

def test_live_stack_smoke():
    r = requests.get("http://localhost:8080")
    assert r.status_code in (200, 404)

def test_live_ask():
    r = requests.post("http://localhost:8080/ask", json={"prompt": "What are the names of the 6 plugins?"})
    assert r.status_code == 200
    data = r.json()
    assert "decision" in data
