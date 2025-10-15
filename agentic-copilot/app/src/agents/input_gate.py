from .formatter import md_mermaid

IN_BOUNDS_HINTS = [
    "unreal", "ue5", "blueprint", "c++", "plugin", "uclass", "uproperty",
    "function", "class", "header", "build.cs", "uasset", "module"
]

def in_bounds(prompt: str) -> bool:
    p = prompt.lower()
    return any(term in p for term in IN_BOUNDS_HINTS)

def handle(prompt: str):
    if not in_bounds(prompt):
        return {"decision": "NO", "reason": "Prompt unrelated to Unreal/game code/plugins."}
    return {"decision": "YES"}
