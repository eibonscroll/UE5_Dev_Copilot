# src/agents/doclink_agent.py
from __future__ import annotations
import re
from typing import List, Dict, Any
from urllib.parse import urlparse

_ALLOWED_HOSTS = {
    "docs.unrealengine.com",
    "dev.epicgames.com",  # official docs often live under /documentation/unreal-engine
}

_DOC_PATH_HINTS = (
    "/en-US/",  # common in docs.unrealengine.com URLs
    "/documentation/unreal-engine",
)

_URL_RE = re.compile(r"https?://[^\s)\]\}>\'\"`]+", re.IGNORECASE)

def _is_unreal_docs(url: str) -> bool:
    try:
        u = urlparse(url)
    except Exception:
        return False
    if u.scheme not in ("http", "https"):
        return False
    if u.netloc not in _ALLOWED_HOSTS:
        return False
    # optional: require a known docs path segment for dev.epicgames.com
    if u.netloc == "dev.epicgames.com" and not any(h in (u.path or "") for h in _DOC_PATH_HINTS):
        return False
    return True

class DocLinkAgent:
    """
    Scans retrieved contexts for official Unreal documentation links and,
    if any are found, appends a "Related Unreal Documentation" section
    to the final markdown.

    It is purely extractive (no web requests) and only surfaces URLs that
    already appear in the retrieved text.
    """

    def __init__(self) -> None:
        pass

    def _extract_links_from_text(self, text: str) -> List[str]:
        if not text:
            return []
        return _URL_RE.findall(text)

    def find_links(self, contexts: List[Dict[str, Any]]) -> List[str]:
        """
        contexts: list of dicts with fields like {"page_content", "text", "path", "source", ...}
        Returns a de-duplicated list of Unreal docs URLs.
        """
        found: List[str] = []
        seen = set()

        for c in contexts or []:
            # support both shapes: page_content (LC Document) or text (your own payload)
            text = c.get("page_content") or c.get("text") or ""
            # also scan path/source — sometimes ingest captured full URLs there
            meta_bits = " ".join([c.get("path") or "", c.get("source") or ""])
            for url in self._extract_links_from_text(text + " " + meta_bits):
                if _is_unreal_docs(url) and url not in seen:
                    seen.add(url)
                    found.append(url)

        return found

    def render_section(self, links: List[str]) -> str:
        if not links:
            return ""
        lines = ["\n---\n", "### Related Unreal Documentation", ""]
        for url in links:
            lines.append(f"- {url}")
        lines.append("")  # trailing newline
        return "\n".join(lines)

    def add_links(self, markdown: str, contexts: List[Dict[str, Any]]) -> str:
        """
        If we discovered official Unreal docs URLs in the provided contexts,
        append a small section with those links.
        """
        links = self.find_links(contexts)
        if not links:
            return markdown
        return (markdown or "") + self.render_section(links)
