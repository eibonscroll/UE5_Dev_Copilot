from ..memory_store import MEMORY

def handle(prompt: str):
    symbols = MEMORY.get_symbols()
    # lightweight heuristic: prefer files with most symbol hits
    top = sorted(symbols, key=lambda e: len(e["classes"])+len(e["functions"]), reverse=True)[:5]
    rationale = []
    for e in top:
        if e["classes"] or e["functions"]:
            rationale.append(f'- **{e["file"]}**: classes {e["classes"][:4]}, funcs {e["functions"][:6]}')
    # Draft response using discovered symbols
    answer = (
        "Based on your request, these files and symbols appear most relevant. "
        "Consider inspecting these classes/functions and their call sites to implement or debug your change."
    )
    return {"answer": answer, "bullets": rationale, "top": top}
