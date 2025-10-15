# utils/filters.py
from __future__ import annotations
from pathlib import Path
import re
import string

# Allowlist aligns with indexer.py
SUPPORTED_EXTS = {
    ".cpp", ".h", ".hpp", ".cs", ".py", ".md", ".uasset.meta", ".ini", ".txt"
}

# Common Unreal/IDE/build noise we should skip
DEFAULT_IGNORE_GLOBS = [
    ".git", ".git/**",
    "**/Binaries/**",
    "**/Intermediate/**",
    "**/Saved/**",
    "**/DerivedDataCache/**",
    "**/.vs/**", "**/.idea/**", "**/.vscode/**",
    "**/node_modules/**",
    "**/Build/**",
    "**/__pycache__/**",
]

_PRINTABLE = set(string.printable)

def is_supported_file(path: Path) -> bool:
    """True if file extension is in the allowlist."""
    return path.is_file() and path.suffix.lower() in SUPPORTED_EXTS

def is_ignored(path: Path, ignore_globs: list[str] = DEFAULT_IGNORE_GLOBS) -> bool:
    """True if the path matches any ignore glob."""
    p = path.as_posix()
    for g in ignore_globs:
        if path.match(g) or _match_posix(p, g):
            return True
    return False

def _match_posix(p: str, glob_pat: str) -> bool:
    """Light wrapper to support simple '**' glob checks on POSIX-like strings."""
    return Path(p).match(glob_pat)

# ---------- Text cleaning pipeline ----------

_BOM = "\ufeff"
_WS_LINE_END = re.compile(r"[ \t]+\n")
_MULTI_BLANKS = re.compile(r"\n{3,}")          # collapse 3+ blank lines
_CRLF = re.compile(r"\r\n?")
_CTRL = re.compile(r"[\x00-\x08\x0B\x0C\x0E-\x1F]")

def strip_bom(text: str) -> str:
    return text.lstrip(_BOM)

def normalize_newlines(text: str) -> str:
    return _CRLF.sub("\n", text)

def strip_trailing_spaces(text: str) -> str:
    return _WS_LINE_END.sub("\n", text)

def collapse_blank_lines(text: str, keep: int = 2) -> str:
    """Collapse runs of blank lines to at most `keep`."""
    if keep < 1:
        keep = 1
    return _MULTI_BLANKS.sub("\n" * keep, text)

def remove_control_chars(text: str) -> str:
    return _CTRL.sub("", text)

def looks_binary(text: str, threshold: float = 0.10) -> bool:
    """
    Heuristic: if >threshold of chars are non-printable (excluding newline/tab),
    treat as binary-like and skip.
    """
    if not text:
        return False
    non_printable = sum(ch not in _PRINTABLE and ch not in "\n\t" for ch in text)
    return (non_printable / max(1, len(text))) > threshold

def truncate_for_chunk(text: str, max_len: int = 5000) -> str:
    """Hard cap to protect the embedder; try to cut at a line boundary."""
    if len(text) <= max_len:
        return text
    cut = text.rfind("\n", 0, max_len)
    return text[: (cut if cut > 0 else max_len)]

def clean_for_embedding(raw: str) -> str | None:
    """
    Apply all cleaning steps. Return None if the text should be skipped.
    """
    if not raw:
        return None
    if looks_binary(raw):
        return None

    t = raw
    t = strip_bom(t)
    t = normalize_newlines(t)
    t = remove_control_chars(t)
    t = strip_trailing_spaces(t)
    t = collapse_blank_lines(t, keep=2)
    t = t.strip()

    if not t:
        return None
    return truncate_for_chunk(t)

__all__ = [
    "SUPPORTED_EXTS",
    "DEFAULT_IGNORE_GLOBS",
    "is_supported_file",
    "is_ignored",
    "clean_for_embedding",
    "looks_binary",
    "truncate_for_chunk",
]
