import re
from pathlib import Path

CPP_FN = re.compile(r'\b([A-Za-z_][A-Za-z0-9_:<>]*)\s+([A-Za-z_][A-Za-z0-9_:<>]*)\s*\([^;]*\)\s*\{?')
UE_CLASS = re.compile(r'\bUCLASS\b|\bclass\s+([A-Za-z_][A-Za-z0-9_:<>]*)')

def extract_symbols(text: str) -> dict:
    fns = [m.group(2) for m in CPP_FN.finditer(text)]
    classes = [m.group(1) for m in UE_CLASS.finditer(text) if m.group(1)]
    return {"functions": list(set(fns)), "classes": list(set(classes))}

def read_text(p: Path) -> str:
    try:
        return p.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return ""
