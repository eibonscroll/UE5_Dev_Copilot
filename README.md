# UE5_Dev_Copilot
Unreal Engine Development Research and Documentation Assistant

# Core Data Flow
```mermaid
flowchart TD
  A[User Prompt] --> B[Input Gate Agent]
  B -->|out-of-bounds| Z[Return "NO"]
  B -->|in-bounds| C[Query Agent]
  C --> D[Vector DB (Qdrant)]
  D --> C
  C --> E[Runtime Memory Store (in-proc)]
  E --> F[Response Agent]
  A --> F
  F --> G[Formatting Agent]
  G --> H[.md with Mermaid]
```

# File Layout
```text
agentic-copilot/
├─ docker-compose.yml
├─ app/
│  ├─ Dockerfile
│  ├─ requirements.txt
│  └─ src/
│     ├─ main.py
│     ├─ settings.py
│     ├─ memory_store.py
│     ├─ indexer.py
│     ├─ embeddings.py
│     ├─ vectordb.py
│     ├─ agents/
│     │  ├─ input_gate.py
│     │  ├─ rag_query.py
│     │  ├─ responder.py
│     │  └─ formatter.py
│     └─ utils/
│        ├─ code_parsing.py
│        └─ filters.py
└─ data/unreal_docs, data/project, data/plugins
```