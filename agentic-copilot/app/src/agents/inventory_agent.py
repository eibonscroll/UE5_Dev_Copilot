# src/agents/inventory_agent.py
from __future__ import annotations
import os
import logging
from typing import Dict, Any, List

log = logging.getLogger("inventory_agent")

PLUGIN_ROOT = "/ingest/plugins"
SKIP_DIRS = {".git", ".vs", "Saved", "DerivedDataCache", "Intermediate", "Binaries"}

def _list_plugin_names(root: str = PLUGIN_ROOT) -> List[str]:
    if not os.path.isdir(root):
        log.warning("inventory_agent: plugin root missing: %s", root)
        return []
    names = []
    for entry in os.listdir(root):
        full = os.path.join(root, entry)
        if not os.path.isdir(full):
            continue
        if entry in SKIP_DIRS:
            continue
        names.append(entry)
    names.sort(key=str.lower)
    return names

def run(query: str) -> Dict[str, Any]:
    """
    InventoryAgent: answers 'plugin list' questions deterministically from the FS.
    Returns a markdown payload that your orchestrator will package like other agents.
    """
    plugins = _list_plugin_names()
    if not plugins:
        md = "No plugins found at `/ingest/plugins`."
        return {
            "decision": "YES",
            "markdown": md,
            "contexts": [{"path": PLUGIN_ROOT, "text": ""}],
            "meta": {"agent": "InventoryAgent", "count": 0}
        }

    md = [
        "### Plugins found",
        "",
        *[f"- {p}" for p in plugins],
        "",
        "_Inventory derived from `/ingest/plugins` folder names (not build artifacts)._",
    ]
    return {
        "decision": "YES",
        "markdown": "\n".join(md),
        "contexts": [{"path": os.path.join(PLUGIN_ROOT, p), "text": ""} for p in plugins],
        "meta": {"agent": "InventoryAgent", "count": len(plugins)}
    }
