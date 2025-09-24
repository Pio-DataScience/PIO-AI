Title: Make the RAG system a production-ready, agentic company assistant

Context
We’re building a domain-aware AI assistant over our company’s data (Oracle AML/BI). We already have retrieval (BM25/FAISS/graph), dictionary embeddings, and a basic web chat. The goal now is to (1) clean the workspace and storage, (2) guarantee complete/consistent dictionary ingestion (283 tables, 7,457 columns), (3) add true agentic behavior with memory and follow-up understanding, and (4) implement structured observability (logging/audit/tracing) across the stack.

Deliverables (all required)
1) Code changes (Python/TypeScript/etc.) with unit/integration tests.
2) One-shot “orchestration script(s)” and CI jobs for ingestion/rebuild (idempotent).
3) Observability pack: JSON logging, OpenTelemetry tracing, metrics.
4) Ops runbook: commands, env vars, rollback steps, SLOs, and health checks.
5) Short architecture doc (1–2 pages) describing agent graph, memory, and safety rails.

--------------------------------------------------------------------------------
TASK 1 — Workspace cleanup & storage migration
Objective
Eliminate CSV usage from pipelines and replace with efficient, columnar Parquet, with schema evolution handled cleanly.

Requirements
- Replace all CSV read/write paths with Parquet (pyarrow).
- Enforce explicit schemas; fail fast on drift; log diffs.
- Add a migration layer to read legacy CSV only during transition, then write Parquet.
- Partition Parquet by logical domains (e.g., owner/table_name) and date where applicable.
- Add a validation step that checks record counts and basic stats before/after migration.

Acceptance Criteria
- No CSVs left in the runtime paths (exclude test fixtures).
- Read/write performance baseline improved (≥2× throughput vs CSV) and recorded in README.
- CI job validates Parquet files (schema + sample read) on PR.

--------------------------------------------------------------------------------
TASK 2 — Dictionary ingestion & embeddings (COMPLETENESS + IDEMPOTENCE)
Objective
Use the full Oracle dictionary coverage: 283 tables and 7,457 columns. Each run must be production-ready and idempotent: fetch full content, (re)embed, and atomically swap collections/indexes.

Requirements
- A single “rebuild_dictionary_embeddings” entrypoint that:
  1) Connects to Oracle (config/env-driven), queries the dictionary view(s).
  2) Verifies counts: EXACTLY 283 tables, 7,457 columns. If not, hard-fail with a drift report.
  3) Generates both table-level and column-level documents (include descriptions, data types, AML/KYC/goAML/FATCA/GATCA flags where available).
  4) Embeds in batches with the configured model (document the model and vector dimension).
  5) Writes to a NEW collection/index; on success, atomically swap alias/pointer (blue/green).
  6) Emits a JSON report: totals, missing descriptions, dimension, timing, and any skipped rows.

- Add incremental mode:
  - Detect new/changed columns (checksum of row payload). Only re-embed changed docs.
  - Full rebuild remains the canonical path for weekly refresh.

- Hard checks:
  - Embedding dimension guard (model vs store). Fail with instructions if mismatch.
  - Duplicate ID prevention and deterministic ID scheme.
  - Backoff/retry around DB and vector-store operations.

Acceptance Criteria
- A single command (e.g., `make build_dictionary_embeddings`) completes end-to-end.
- Post-run report shows 283/7,457 coverage with zero unembedded items.
- Blue/green alias switch verified; rollback works.
- CI job runs dry-run validation (schema only) on PR and full build on main (nightly).

--------------------------------------------------------------------------------
TASK 3 — Agentic behavior, memory, and follow-ups (LangGraph or equivalent)
Objective
Move from “single-turn prompt + retrieval” to a multi-tool, stateful agent that understands context and can choose actions (plan → act → observe → re-plan), including executing SQL when needed.

Agent Graph (minimum)
- Router Node: Classifies query (schema lookup / data question / analytical request / general).
- Retrieval Node: Uses hybrid retrieval (BM25/FAISS/graph) to fetch docs/schema as needed.
- SQL-Author Node: When the intent implies data analysis (counts/nulls/aggregates), generate validated SQL for Oracle.
- Executor Node: Executes SQL safely (read-only by default), returns results (tabular).
- Answer Composer: Grounds final answer in cited docs/data and prior turns.
- Memory Node: Maintains conversation state.

Memory & Context
- Short-term memory: sliding window of recent turns + tool outputs.
- Long-term memory: per-session summary (compact), plus cached table schemas for speed.
- Storage: use a fast key-value store (Redis/Postgres) via the framework’s checkpointing API.
- Include a “follow-up detector” (e.g., based on coreference + discourse cues). If detected, pass prior turn entities (table names, selected columns, filters) into the next tool call.

Follow-up Example (must support)
User: “What columns are in PIO_AML_TRANSACTIONS?”  
→ Router→Retrieval→Answer with schema.  
User: “Which columns have NULLs and how many?”  
→ Follow-up detector resolves table; Router engages SQL-Author Node; generate COUNT(*) and COUNT(column) filters; Executor runs query; Answer Composer returns a table of null counts with clear caveats.

Safety & Guardrails
- Read-only by default; any write/side-effect requires explicit “APPROVAL_REQUIRED” state.
- Strict grounding: never invent columns. Validate SQL against known schema first.
- Timeouts, retries, and loop limit with a graceful “I’m stuck” recovery suggestion.

Acceptance Criteria
- The above follow-up scenario passes end-to-end without user re-stating the table.
- Session summaries are persisted and reused across turns within a session.
- SQL is validated against schema before execution; on mismatch, auto-correct and retry once.

--------------------------------------------------------------------------------
TASK 4 — Structured logging, auditing, and tracing (NO prints, NO emojis)
Objective
Replace ad-hoc prints with production observability: structured logs, distributed tracing, and metrics for auditability and troubleshooting.

Requirements
- Logging: Python `logging` or equivalent with JSON layout; one line per event; include level, timestamp, service, correlation_id/trace_id, user/session_id (hashed), phase, duration_ms, tool_name, and outcome.
- Tracing: OpenTelemetry spans around key phases (routing, retrieval, embedding, SQL gen, execution, compose). Export to OTLP endpoint (configurable).
- Metrics: counters (queries_total, tool_calls_total, sql_exec_total, errors_total), histograms (latency per phase), gauges (embed_queue_depth).
- Redaction: never log PII or raw SQL params; use parameterized logs with safe previews.
- Audit Trail: persist a minimal per-request audit record (who, what, when, tools used, references returned, final answer length, confidence/grounding score).

Acceptance Criteria
- All components emit JSON logs; grep-able by correlation_id across services.
- Traces show end-to-end spans with child tool spans and error tags.
- A “health check” endpoint exposes basic metrics (or push to the metrics backend).
- No print statements or emojis remain in production code paths.

--------------------------------------------------------------------------------
TASK 5 — Performance, scalability, and resilience
Requirements
- Result caching for repeated identical tool calls within a session (schema + small SQL results).
- Concurrency controls and async I/O for Oracle reads (pooling, statement cache).
- Backpressure on embedding jobs; bounded batch sizes; exponential backoff on failure.
- Config management via environment/12-factor; feature flags for agent behaviors.

Acceptance Criteria
- Load test plan included; latency p50/p95 recorded for: routing, retrieval, SQL, compose.
- Graceful degradation: if vector search fails, fallback to BM25; if LLM provider A fails, failover to provider B.
- Clear error messages to the user when recovery paths are exhausted.

--------------------------------------------------------------------------------
Coding Standards & Testing
- Type hints, docstrings, and module headers.
- Unit tests for router, memory store, SQL validator, and ingestion utilities.
- Integration tests: end-to-end “follow-up” scenario + dictionary rebuild dry-run.
- Lint/format enforced in CI; security scan for secrets in logs/configs.

Runbook (put in README)
- How to: full rebuild vs incremental; rotate collections (blue/green); rollback.
- How to: enable/disable agent nodes via config.
- Health checks and troubleshooting (common error codes/messages).

Non-Goals (for clarity)
- No production write-operations to Oracle yet (read-only analytics only).
- No model fine-tuning in this milestone (prompting + retrieval only).

CONFIG to expose (examples)
- ORACLE_DSN, ORACLE_USER, ORACLE_PASSWORD (secrets via vault/env).
- EMBEDDING_MODEL_ID, EMBEDDING_DIMENSION.
- VECTOR_STORE_* (path/URI, collection aliases).
- OTEL_EXPORTER_OTLP_ENDPOINT, LOG_LEVEL, FEATURE_FLAGS.

Definition of Done
- All acceptance criteria met across Tasks 1–5.
- CI green; reproducible builds; docs updated.
- A demo script runs the follow-up scenario start-to-finish with logs and traces visible.
