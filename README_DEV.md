Copilot, build the codebase exactly as specified

Context
We have a repo with this package root: pio-ai/ (Python 3.10+).
Everything must import using from pio-ai.....
All paths must anchor off Path(pio-ai.__file__).resolve().parent so nothing depends on terminal CWD.

Goal
Implement a local, offline-friendly RAG system over my code/projects + DB dictionary with:

AST symbol index (done already; keep as is),

Call & Import graph index (YOU implement),

BM25 keyword index,

FAISS vector index (code + prose spaces),

Hybrid retriever (BM25 + FAISS + ±1 hop graph expand + AST line snap),

Tools API (read_file, where_is_line, schema, search_repo),

LLM provider wrapper (OpenAI for POC; local later),

Simple FastAPI /ask endpoint + small CLI utilities.

Follow this exact structure (create missing files/folders):

PIO-AI/
  __init__.py
  config/
    app.yaml                 # already exists; if missing, create defaults
    .env                     # NOT committed; read with python-dotenv
  indexes/
    bm25/                    # per-project folders
    faiss_code/
    faiss_text/
    graph/
    symbols/                 # already created by AST step
  services/
    ingest/
      __init__.py
      manifest_reader.py         # read warehouse/manifest.yaml
      normalizer.py              # path/encoding/nb->py helpers
      db_dict.py                 # schema dictionary read (YAML/SQLite; no PII)
    indexer/
      __init__.py
      ast_index.py               # (keep as implemented)
      graph_index.py             # (YOU implement per spec below)
      bm25_index.py              # (YOU implement)
      faiss_index.py             # (YOU implement; two spaces: code/text)
    retriever/
      __init__.py
      router.py                  # classify query type
      hybrid.py                  # orchestrate BM25+FAISS+graph; merge/rerank
      pack_context.py            # assemble final context + excerpts + citations
    tools_api/
      __init__.py
      fs_tools.py                # read_file(), list_dir_safe()
      ast_tools.py               # where_is_line() using symbols DB
      schema_tools.py            # schema(table/column) from db_dict
      search_tools.py            # BM25 grep-like search
    llm/
      __init__.py
      provider.py                # OpenAI/local switch; chat() function
      prompts.py                 # templates for code/doc/schema answers
      answer.py                  # final formatting + citations
    api/
      __init__.py
      server.py                  # FastAPI app with /ask
  scripts/
    __init__.py
    00_validate_manifest.py
    10_ingest_dryrun.py
    21_build_ast_index.py
    22_where_is_line.py
    23_build_graph_index.py
    24_show_neighbors.py
    31_build_bm25.py
    32_build_faiss.py
    40_serve_api.py

Global coding rules

Use type hints, docstrings, Pathlib, and rich for CLI output.

Read .env via python-dotenv in llm/provider.py.

SQLite for all indexes; WAL mode; create indexes for hot fields.

Windows-safe path handling; store POSIX relative paths inside indexes for consistency.

1) Call & Import Graph — services/indexer/graph_index.py

Implement:

expand_files(root, includes, excludes) -> list[Path]
Reuse logic from AST step; return only .py.

parse_graph_for_file(root, file_path) -> (imports, calls)
Walk AST: collect

Imports: (file_path_rel, kind: "import"/"importfrom", module, name, asname)

Calls: (file_path_rel, caller_qual, callee_name, lineno) where:

caller_qual = <module_path_dotted>[.Class][.func]

callee_name = dotted from ast.Attribute/ast.Name (best-effort)

SQLite schema:

files(path PK)

imports(id, file_path, kind, module, name, asname)

calls(id, file_path, caller_qual, callee_name, lineno)

Indexes on imports.file_path, calls.file_path, calls.caller_qual, calls.callee_name

build_project_graph(project_name, root, includes, excludes, out_db) -> dict
Clear + rebuild. Return counts.

Query helpers for the explorer: callees_of(con, caller_qual), callers_of(con, callee_name).

CLI: scripts/23_build_graph_index.py builds for all projects into indexes/graph/{project}.sqlite.
Explorer: scripts/24_show_neighbors.py shows callers/callees.

2) BM25 Keyword Index — services/indexer/bm25_index.py

Implement using Whoosh (or equivalent pure-Python):

Per-project directory in indexes/bm25/{project}/.

Index text of files you ingest (code and docs), storing:

project, path_posix, kind (code|text), text

Tokenization: simple analyzer with casefold; keep underscores and dots (good for symbols).

APIs:

build_bm25_for_project(project_name, files: list[(abs_path, rel_posix, kind)], out_dir: Path) -> stats

search_bm25(project_name, query: str, top_k: int) -> list[dict] with fields (path, score, snippet)

CLI: scripts/31_build_bm25.py

Read manifest, collect files similarly to AST step.

Text rules:

For .py & .sql → kind="code".

For .md/.txt/.yaml/.yml/.json/.toml → kind="text".

Skip binaries.

3) FAISS Vector Index — services/indexer/faiss_index.py

Implement two spaces:

faiss_code/ for code-like files (.py, .sql, .yaml, configs)

faiss_text/ for prose/docs (.md, .txt, README, comments)
Embedding

Provide an interface embed_texts(texts: list[str], space: Literal["code","text"]) -> np.ndarray.

For POC, stub with deterministic hashing → random stable vectors (so the pipeline runs without online calls). Keep code ready to swap to real embeddings later.

FAISS index: IndexFlatIP (cosine via normalized vectors).

Store sidecar SQLite/JSON for mapping vector id → {project, path_posix, kind, span (optional), preview}.

APIs:

build_faiss_for_project(project_name, items, out_dir_code, out_dir_text) -> stats

search_faiss(project_name, query, space, top_k) -> list[dict]

CLI: scripts/32_build_faiss.py.

4) Tools API — services/tools_api/*

fs_tools.py

read_file(project: str, rel_posix: str, start: int, end: int) -> str

Validate path exists under manifest project root; clamp line range; return text.

ast_tools.py

where_is_line(project: str, rel_posix: str, line: int) -> dict | None

Uses indexes/symbols/{project}.sqlite

schema_tools.py

describe_table(name), describe_column(table, column)

Load from warehouse/db/oracle/{ddl,comments,relationships,profiles} if present.

search_tools.py

grep(project: str, query: str, top_k: int) -> list[dict]

Calls BM25 search and returns path, score, snippet.

5) Retriever — services/retriever/*

router.py

Classify query into: "line_code" | "code" | "schema" | "doc".

Heuristics:

Matches path:line → line_code

Contains table/column patterns TABLE.COL → schema

Otherwise default "code" if code-y tokens present; else "doc".

hybrid.py

For "line_code": use ast_tools.where_is_line to get enclosing node; then expand with graph neighbors (±1 hop) and BM25 exact match on key tokens from the node text.

For "code": BM25 top_k + FAISS(code) top_k → merge de-dup (RRf or weighted sum). Expand ±1 hop neighbors via graph.

For "doc": BM25 + FAISS(text).

For "schema": use schema_tools first; if not found, fallback BM25.

pack_context.py

Given a set of hits {project, path, start_line?, end_line?, kind, snippet}, open files and assemble excerpts (for code: function/class blocks via symbols DB; for docs: paragraph windows).

Return (final_context_str, citations: list[ {project, path, start, end} ]).

6) LLM — services/llm/*

provider.py

.env keys: PROVIDER=openai|local, OPENAI_API_KEY, LOCAL_LLM_BASE_URL, etc.

chat(messages: list[dict], model: Optional[str]=None) -> str

Implement OpenAI-compatible call for "openai"; for "local" just echo mock (so pipeline runs).

prompts.py

Templates: CODE_PROMPT, DOC_PROMPT, SCHEMA_PROMPT, LINE_PROMPT.

Always instruct: use only provided context; include citations (path:start-end).

answer.py

compose_answer(query, context, citations) -> str

Wrap the LLM call and post-process to append a neat “Sources” block.

7) API — services/api/server.py

FastAPI app:

POST /ask with {"query": "...", "project": "AI_AML", "path": "...", "line": 123 (optional)}

Pipeline: route → retrieve → pack → LLM → return {answer, citations}

Add CLI launcher scripts/40_serve_api.py:

import uvicorn, pio-ai
from pathlib import Path
uvicorn.run("pio-ai.services.api.server:app", host="127.0.0.1", port=8008, reload=False)

8) Scripts — finish the set

Make these runnable with python -m pio-ai.scripts.NAME:

31_build_bm25.py — build BM25 for all projects

32_build_faiss.py — build FAISS for all projects

(already have) 23_build_graph_index.py, 24_show_neighbors.py

40_serve_api.py — start the FastAPI server

Each script should:

Read warehouse/manifest.yaml

Print per-project stats with rich

Exit non-zero on errors

9) Acceptance tests (quick)

After building indexes, run:

23_build_graph_index.py: print files/imports/calls counts > 0 for code-heavy projects.

31_build_bm25.py: confirm index dir created and query "AML_REASON_COLS" returns at least 1 hit.

32_build_faiss.py: confirm both faiss_code/ and faiss_text/ get populated; a query returns results.

22_where_is_line.py --project AI_AML --path src/utils/system_monitoring/path_resolver.py --line 42 returns a function or class.

Start API, POST /ask with:

"what does AML_REASON_COLS mean?" → answer + citations to schema/docs.

"explain line 278 in src/aml/local_outlier.py" → answer cites that file:line and nearest helpers (±1 hop).

"where is normalize_txn used?" → returns callers via BM25/graph hybrid.

10) Non-functional requirements

No network required to build indexes (FAISS can be stubbed with deterministic embeddings now).

All indexes are disposable: safe to delete/rebuild.

Log to pio-ai/logs/ with timestamps.

Keep code small, clear, and commented; raise ValueError with helpful messages when inputs are missing (e.g., unknown project).

Now implement all missing modules and scripts per this spec.