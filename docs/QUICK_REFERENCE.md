# Production Agentic Assistant - Quick Reference

## Component Overview

| Component | File | Key Classes | Purpose |
|-----------|------|-------------|---------|
| **Memory** | `enhanced_memory.py` | `EnhancedConversationMemory` | Multi-tier conversation memory |
| **Auto-Traversal** | `auto_traversal.py` | `AutoTraversalEngine` | Query expansion & context |
| **Edge Cases** | `edge_case_handler.py` | `EdgeCaseOrchestrator` | Graceful degradation |
| **Safety** | `safety_guards.py` | `ComprehensiveSafetyGuards` | SQL validation & compliance |
| **Schema** | `schema_overview.py` | `SchemaRepository` | Cached metadata access |
| **Orchestrator** | `enhanced_orchestrator.py` | `EnhancedProductionOrchestrator` | StateGraph workflow |
| **Observability** | `enhanced_observability.py` | `EnhancedObservability` | Structured logging |
| **Integration** | `production_integration.py` | `ProductionAgenticAssistant` | Unified interface |

## Quick Start (3 Steps)

```python
# 1. Import
from services.agents.production_integration import ProductionAgenticAssistant

# 2. Initialize
assistant = ProductionAgenticAssistant(
    llm_client=your_llm,
    catalog_db_path=Path("warehouse/catalog.db")
)

# 3. Use
result = assistant.chat("Your query here")
print(result['answer'])
```

## Common Usage Patterns

### Basic Query
```python
result = assistant.chat("What tables have customer data?")
```

### With Session Tracking
```python
result = assistant.chat(
    query="Show high-risk customers",
    session_id="session-123",
    user_id="analyst-456"
)
```

### Follow-up Question
```python
result1 = assistant.chat("What is in the CUSTOMER table?", session_id="s1")
result2 = assistant.chat("Show me those columns", session_id="s1")  # Context maintained
```

## Configuration

### Memory Settings
```python
memory = EnhancedConversationMemory(
    short_term_window=10,      # Last 10 turns
    episodic_threshold=5,      # Summarize every 5 turns
    storage_path=Path("memory/sessions")
)
```

### Safety Settings
```python
guards = ComprehensiveSafetyGuards()
# SQL Validator: SELECT-only, no injection
# Abuse Detector: Rate limiting, profanity filter
# Answer Reviewer: PII redaction, compliance
```

### Cache Settings
```python
repo = SchemaRepository(
    catalog_db_path=Path("warehouse/catalog.db"),
    cache_ttl=300  # 5 minutes
)
```

## Observability

### Start Tracing
```python
obs = get_observability()
trace = obs.start_trace(session_id="s1", user_id="u1")
```

### Trace Operation
```python
with obs.trace_operation("my_operation", trace_context=trace):
    # Your code here
    pass
```

### Get Metrics
```python
metrics = obs.get_metrics_summary()
print(f"Avg latency: {metrics['operations']['query.process']['avg_ms']}ms")
```

### Export Metrics
```python
obs.export_metrics(Path("data/observability/metrics.json"))
```

## Error Handling

### Automatic Fallback
The system automatically handles:
- Missing embeddings → BM25 fallback
- Empty results → Helpful suggestions
- SQL errors → Retry or safe error message
- Ambiguous intent → Clarifying questions

### Manual Error Handling
```python
try:
    result = assistant.chat("query")
except Exception as e:
    # Check logs with trace_id
    trace_id = result.get('trace_id')
    # Review structured logs for debugging
```

## Monitoring

### Key Metrics
```python
# Cache performance
cache_stats = assistant.get_cache_stats()
hit_rate = cache_stats['hit_rate']  # Target: >70%

# Query metrics
metrics = assistant.observability.get_metrics_summary()
avg_latency = metrics['operations']['query.process']['avg_ms']  # Target: <500ms
error_rate = metrics['total_errors']  # Target: <5%
```

### Log Locations
- **Console**: Real-time structured JSON
- **File**: `logs/production_agent.log`
- **Metrics**: `data/observability/metrics.json`

## Safety Checks

### SQL Validation
```python
result = guards.validate_sql("SELECT * FROM users WHERE id = 1")
if not result.safe:
    print(result.reason)
    print(result.violations)
```

### Query Check
```python
result = guards.check_query("show me passwords", user_id="user-123")
if not result.safe:
    # Query blocked
    pass
```

### Answer Review
```python
result = guards.review_answer("User email is john@example.com")
if result.sanitized_content:
    # Use sanitized version
    answer = result.sanitized_content
```

## Debugging

### Enable Debug Logging
```python
configure_observability(log_level="DEBUG")
```

### Find Query Trace
1. Get `trace_id` from result
2. Search logs: `grep "trace_id":"abc-123" logs/production_agent.log`
3. View full execution path

### Common Issues

**High Latency**
- Check cache hit rate
- Verify database connection
- Review slow operations in metrics

**Low Accuracy**
- Enable auto-traversal
- Enrich schema metadata
- Review entity extraction patterns

**Safety Violations**
- Check SQL patterns in logs
- Review constitutional rules
- Verify answer sanitization

## Best Practices

1. **Always use session IDs** for multi-turn conversations
2. **Monitor cache hit rates** weekly
3. **Export metrics hourly** for analysis
4. **Review safety violations** daily
5. **Prune old sessions** monthly
6. **Update schema cache** when DDL changes
7. **Test with DEBUG logs** before production
8. **Set up alerts** on error rates

## Performance Targets

| Metric | Target | Alert Threshold |
|--------|--------|-----------------|
| Latency (cached) | <200ms | >1000ms |
| Cache Hit Rate | >70% | <50% |
| Error Rate | <2% | >10% |
| Fallback Rate | <10% | >30% |
| Memory per Session | <100KB | >1MB |

## Architecture Diagram

```
User Query
    ↓
Safety Check → [BLOCKED] → End
    ↓ [SAFE]
Intent Classification
    ↓
Auto-Traverse → Entity Extraction
    ↓            Schema Search
    ↓            Graph Traversal
Schema Retrieval (with cache)
    ↓
SQL Generation (if needed)
    ↓
SQL Validation → [UNSAFE] → Retry
    ↓ [SAFE]
SQL Execution
    ↓
Answer Composition
    ↓
Answer Review → [SANITIZE] → Redact
    ↓ [APPROVED]
Final Answer
    ↓
Memory Storage
    ↓
Metrics Export
```

## API Reference

### ProductionAgenticAssistant

**Methods**:
- `chat(query, session_id, user_id)` → Response dict
- `get_schema_overview()` → Schema summary string
- `get_table_info(table_name)` → Table details string
- `export_metrics(path)` → Export to file
- `get_cache_stats()` → Cache statistics dict

### Response Format
```python
{
    'answer': str,           # Final answer
    'trace_id': str,         # Trace identifier
    'intent': str,           # Classified intent
    'sql_used': str,         # SQL query (if any)
    'fallback_used': bool,   # Whether fallback was used
    'metrics': {
        'total_duration_ms': float,
        'by_node': {...}
    },
    'trace_summary': {...}   # Full trace details
}
```

## Links

- **Full Documentation**: `docs/PRODUCTION_ENHANCEMENTS_GUIDE.md`
- **Implementation Summary**: `docs/IMPLEMENTATION_SUMMARY.md`
- **Build Document**: `bulid.md`

---

**Version**: 1.0  
**Last Updated**: October 3, 2025  
**Status**: Production Ready ✓
