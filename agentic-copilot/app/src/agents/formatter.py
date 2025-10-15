def md_mermaid(title: str, bullets: list[str], top_files: list[dict], prompt: str) -> str:
    graph = "flowchart LR\n"
    graph += '  U[User Prompt] -->|in-bounds| Q[RAG Query]\n'
    for i, e in enumerate(top_files[:4]):
        node = f'N{i}["{e["file"].split("/")[-1]}\\nC:{len(e["classes"])} F:{len(e["functions"])}"]'
        graph += f"  Q --> {node}\n"
    graph += "  Q --> R[Response Draft]\n  R --> F[Formatted Markdown]\n"

    md = f"# Agentic Copilot Response\n\n**Prompt**: `{prompt}`\n\n"
    md += "## Suggested Targets\n" + "\n".join(bullets) + "\n\n"
    md += "## Call Graph Sketch\n\n```mermaid\n" + graph + "```\n"
    return md
