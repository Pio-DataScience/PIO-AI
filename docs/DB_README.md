# Oracle Database Metadata Support for PIO-AI

## Overview

This document describes the Oracle database metadata support extension for PIO-AI, providing comprehensive AML (Anti-Money Laundering) domain metadata harvesting, relationship graph building, and schema Q&A capabilities.

## Architecture

### Core Components

```
services/db/
├── oracle_conn.py          # Oracle connection pool with circuit breaker
├── catalog_store.py        # SQLite catalog storage
├── metadata_harvester.py   # Oracle DBA_* metadata extraction
├── classifiers.py          # PII detection heuristics
└── relationship_builder.py # NetworkX relationship graphs

services/retriever/
└── schema_retriever.py     # BM25+embedding schema search

scripts/
├── 41_build_aml_catalog.py   # Metadata harvesting
├── 42_embed_aml_catalog.py   # Embedding generation
├── 43_build_aml_relgraph.py  # Relationship graph building
└── 44_export_erd.py          # ERD export (DOT/GraphML/Mermaid)
```

### Safety Architecture

- **Metadata-Only Access**: Uses DBA_*/ALL_* views exclusively, no row data access
- **Parameterized Queries**: All SQL uses parameter binding to prevent injection
- **Circuit Breaker**: Automatic failure protection with exponential backoff
- **Connection Pooling**: Efficient Oracle connection management
- **PII Classification**: Automatic detection and marking of sensitive columns

## Setup Instructions

### 1. Dependencies

Install required Python packages:

```bash
pip install cx_Oracle networkx sqlite3 pyyaml
```

### 2. Oracle Database Access

Ensure your Oracle user has the following privileges:

```sql
-- Metadata read access
GRANT SELECT ON DBA_TABLES TO your_user;
GRANT SELECT ON DBA_TAB_COLUMNS TO your_user;
GRANT SELECT ON DBA_CONSTRAINTS TO your_user;
GRANT SELECT ON DBA_CONS_COLUMNS TO your_user;
GRANT SELECT ON DBA_VIEWS TO your_user;
GRANT SELECT ON DBA_TAB_COMMENTS TO your_user;

-- Alternative: Use ALL_* views if DBA_* access not available
GRANT SELECT ON ALL_TABLES TO your_user;
GRANT SELECT ON ALL_TAB_COLUMNS TO your_user;
-- ... (similar for other ALL_* views)
```

### 3. Configuration

Create or update `config/database.yaml`:

```yaml
oracle:
  host: "${ORACLE_HOST:localhost}"
  port: "${ORACLE_PORT:1521}"
  service_name: "${ORACLE_SERVICE:ORCL}"
  user: "${ORACLE_USER:aml_reader}"
  password: "${ORACLE_PASSWORD:}"
  
  # Connection pool settings
  pool:
    min_connections: 2
    max_connections: 10
    timeout: 30
    retry_count: 3

aml:
  # AML domain scope
  owners:
    - "AML_PROD"
    - "AML_STAGE"
    - "REFERENCE"
  
  # Table name patterns
  table_patterns:
    - ".*CUSTOMER.*"
    - ".*ACCOUNT.*"
    - ".*TRANSACTION.*"
    - ".*ALERT.*"
    - ".*CASE.*"
    - ".*PARTY.*"
    - ".*SANCTION.*"

catalog:
  path: "indexes/graph/AML.sqlite"
  
graphs:
  export_dir: "warehouse/graphs"
```

### 4. Environment Variables

Set up your environment:

```bash
# Windows PowerShell
$env:ORACLE_HOST = "your-oracle-host"
$env:ORACLE_PORT = "1521"
$env:ORACLE_SERVICE = "your-service"
$env:ORACLE_USER = "your-username"
$env:ORACLE_PASSWORD = "your-password"

# Linux/macOS
export ORACLE_HOST="your-oracle-host"
export ORACLE_PORT="1521"
export ORACLE_SERVICE="your-service"
export ORACLE_USER="your-username"
export ORACLE_PASSWORD="your-password"
```

## Usage Guide

### 1. Harvest Metadata

Extract Oracle metadata for AML domain:

```bash
# Build complete catalog
python scripts/41_build_aml_catalog.py

# Build specific components
python scripts/41_build_aml_catalog.py --tables-only
python scripts/41_build_aml_catalog.py --views-only
python scripts/41_build_aml_catalog.py --constraints-only

# Custom scope
python scripts/41_build_aml_catalog.py --owners AML_PROD,STAGING --patterns ".*CUSTOMER.*,.*ACCOUNT.*"

# Verbose logging
python scripts/41_build_aml_catalog.py --verbose
```

### 2. Generate Embeddings

Create embeddings for semantic search:

```bash
# Generate all embeddings
python scripts/42_embed_aml_catalog.py

# Tables only
python scripts/42_embed_aml_catalog.py --entity-types table

# Custom batch size
python scripts/42_embed_aml_catalog.py --batch-size 50

# Force regeneration
python scripts/42_embed_aml_catalog.py --force-regen
```

### 3. Build Relationship Graph

Construct FK→PK relationship mappings:

```bash
# Build complete graph
python scripts/43_build_aml_relgraph.py

# Analyze existing graph
python scripts/43_build_aml_relgraph.py --analyze-only

# Custom quality threshold
python scripts/43_build_aml_relgraph.py --min-quality 0.8

# Export graph data
python scripts/43_build_aml_relgraph.py --export-json graph_data.json
```

### 4. Export ERD Diagrams

Generate entity relationship diagrams:

```bash
# All formats
python scripts/44_export_erd.py

# Specific formats
python scripts/44_export_erd.py --fmt dot
python scripts/44_export_erd.py --fmt graphml,mermaid

# Custom output directory
python scripts/44_export_erd.py --output-dir "output/diagrams"

# List available formats
python scripts/44_export_erd.py --list-formats
```

## API Documentation

### Oracle Connection Pool

```python
from services.db import OracleConnectionPool

# Initialize connection pool
pool = OracleConnectionPool(config['oracle'])

# Execute query safely
with pool.get_connection() as conn:
    result = pool.execute_query(
        conn,
        "SELECT owner, table_name FROM dba_tables WHERE owner = :owner",
        {"owner": "AML_PROD"}
    )
```

### Catalog Store

```python
from services.db import CatalogStore

# Initialize catalog
catalog = CatalogStore("indexes/graph/AML.sqlite")

# Add table metadata
catalog.upsert_table(
    owner="AML_PROD",
    table_name="CUSTOMERS",
    tablespace_name="AML_DATA",
    num_rows=50000
)

# Query tables
tables = catalog.get_all_tables()
columns = catalog.get_table_columns("AML_PROD", "CUSTOMERS")

# Health check
health = catalog.health_check()
print(f"Status: {health['status']}")
print(f"Tables: {health['catalog_tables']}")
```

### Schema Retriever

```python
from services.retriever import SchemaRetriever

# Initialize retriever
retriever = SchemaRetriever(catalog)

# Search for entities
results = retriever.search("customer email address", top_k=5)
for result in results:
    print(f"{result.entity_type}: {result.name} - {result.description}")

# Find join path
path = retriever.find_join_path("AML_PROD.CUSTOMERS", "AML_PROD.TRANSACTIONS")
if path:
    print(f"Join path: {' -> '.join(path.tables)}")
    for condition in path.join_conditions:
        print(f"  {condition}")

# Generate SQL
sql = retriever.generate_synthetic_sql(
    "find high-risk customers with large transactions",
    tables=["AML_PROD.CUSTOMERS", "AML_PROD.ACCOUNTS", "AML_PROD.TRANSACTIONS"]
)
print(sql)
```

### Relationship Builder

```python
from services.db import RelationshipBuilder

# Initialize builder
builder = RelationshipBuilder(catalog)

# Build relationship graph
builder.build_relationships()

# Get statistics
stats = builder.get_graph_statistics()
print(f"Nodes: {stats['nodes']}, Edges: {stats['edges']}")

# Find shortest path
path = builder.find_shortest_path("AML_PROD.CUSTOMERS", "AML_PROD.TRANSACTIONS")

# Export relationships
relationships = builder.export_relationships()
```

## Query Examples

### Schema Search Queries

```python
# Find customer-related entities
results = retriever.search("customer personal information PII")

# Find transaction analysis tables
results = retriever.search("financial transactions money transfer")

# Find AML monitoring components
results = retriever.search("alerts cases suspicious activity monitoring")

# Find reference data
results = retriever.search("sanctions watchlist country codes")
```

### SQL Generation

```python
# Customer due diligence
sql = retriever.generate_synthetic_sql(
    "show customer profile with account summary and risk indicators",
    tables=["AML_PROD.CUSTOMERS", "AML_PROD.ACCOUNTS", "AML_PROD.RISK_SCORES"]
)

# Transaction monitoring
sql = retriever.generate_synthetic_sql(
    "find large cash transactions above threshold for specific time period",
    tables=["AML_PROD.TRANSACTIONS", "AML_PROD.ACCOUNTS", "AML_PROD.CUSTOMERS"]
)

# Alert investigation
sql = retriever.generate_synthetic_sql(
    "analyze alert patterns for high-risk customers",
    tables=["AML_PROD.ALERTS", "AML_PROD.CUSTOMERS", "AML_PROD.CASES"]
)
```

## Error Handling

### Common Issues

1. **Oracle Connection Failures**
   ```
   ORA-12170: TNS:Connect timeout occurred
   ```
   - Check network connectivity
   - Verify Oracle service status
   - Adjust timeout settings in config

2. **Permission Denied**
   ```
   ORA-00942: table or view does not exist
   ```
   - Verify DBA_* or ALL_* view access
   - Check user privileges
   - Use appropriate view prefix

3. **Circuit Breaker Activated**
   ```
   CircuitBreakerError: Circuit breaker is OPEN
   ```
   - Wait for automatic reset
   - Check Oracle health
   - Review connection pool settings

### Debugging

Enable verbose logging:

```python
import logging
logging.basicConfig(level=logging.DEBUG)

# All database operations will show detailed logs
```

Check catalog health:

```python
health = catalog.health_check()
if health['status'] != 'healthy':
    print(f"Catalog issues: {health}")
```

## Performance Tuning

### Oracle Optimization

1. **Use appropriate views**:
   - `DBA_*` views for full database access
   - `ALL_*` views for accessible objects only
   - `USER_*` views for owned objects

2. **Limit scope**:
   - Configure specific owners in `aml.owners`
   - Use table patterns to filter relevant tables
   - Set reasonable batch sizes for large schemas

3. **Connection pooling**:
   - Adjust `min_connections` and `max_connections`
   - Set appropriate `timeout` values
   - Monitor connection usage

### Catalog Performance

1. **Indexing**:
   - Catalog automatically creates indexes on key columns
   - Regular VACUUM for SQLite optimization

2. **Batch operations**:
   - Use batch sizes for embedding generation
   - Process large schemas in chunks

3. **Memory usage**:
   - NetworkX graphs kept in memory
   - Consider disk-based storage for very large schemas

## Security Considerations

### Data Protection

1. **No Row Data Access**:
   - System only accesses metadata, never actual row data
   - All queries use `DBA_*` and `ALL_*` views exclusively

2. **PII Detection**:
   - Automatic classification of sensitive columns
   - PII flags stored in catalog for audit purposes

3. **Query Safety**:
   - All SQL uses parameterized queries
   - No dynamic SQL construction from user input

### Access Control

1. **Minimal Privileges**:
   - Oracle user needs only metadata view access
   - No INSERT, UPDATE, DELETE permissions required

2. **Environment Variables**:
   - Credentials stored in environment, not config files
   - Use secure credential management in production

3. **Audit Trail**:
   - All operations logged with timestamps
   - Circuit breaker events recorded
   - Query hashes for security analysis

## Operational Procedures

### Daily Operations

1. **Health Monitoring**:
   ```bash
   python -c "
   from services.db import CatalogStore
   catalog = CatalogStore('indexes/graph/AML.sqlite')
   print(catalog.health_check())
   "
   ```

2. **Catalog Refresh**:
   ```bash
   # Full refresh (weekly)
   python scripts/41_build_aml_catalog.py --force-refresh
   
   # Incremental refresh (daily)
   python scripts/41_build_aml_catalog.py --incremental
   ```

### Maintenance

1. **Cleanup Old Data**:
   ```bash
   # Remove old embeddings
   python scripts/42_embed_aml_catalog.py --cleanup-old --days 30
   
   # Compact catalog
   sqlite3 indexes/graph/AML.sqlite "VACUUM;"
   ```

2. **Backup Procedures**:
   ```bash
   # Backup catalog
   cp indexes/graph/AML.sqlite backups/AML_$(date +%Y%m%d).sqlite
   
   # Backup configuration
   cp config/database.yaml backups/database_$(date +%Y%m%d).yaml
   ```

### Monitoring

1. **Circuit Breaker Status**:
   - Monitor logs for circuit breaker events
   - Alert on repeated failures
   - Track connection pool utilization

2. **Performance Metrics**:
   - Query execution times
   - Catalog size growth
   - Graph complexity metrics

## Troubleshooting

### Common Scenarios

1. **No Tables Found**:
   - Check `aml.owners` configuration
   - Verify Oracle user has access to specified schemas
   - Review `table_patterns` filters

2. **Poor Search Results**:
   - Regenerate embeddings with `--force-regen`
   - Check embedding model configuration
   - Verify catalog completeness

3. **Missing Relationships**:
   - Run constraint analysis: `43_build_aml_relgraph.py --analyze-only`
   - Lower quality threshold: `--min-quality 0.5`
   - Check foreign key constraint definitions

4. **Export Failures**:
   - Verify output directory exists and is writable
   - Check graph completeness
   - Review NetworkX installation

### Support Contacts

For technical issues:
- Check logs in `logs/` directory
- Review catalog health status
- Examine circuit breaker state
- Verify Oracle connectivity

## Appendix

### Sample Configuration Files

#### Minimal Configuration
```yaml
oracle:
  host: "localhost"
  port: 1521
  service_name: "ORCL"
  user: "aml_reader"
  password: "password"

aml:
  owners: ["AML_PROD"]
  table_patterns: [".*"]

catalog:
  path: "aml_catalog.db"
```

#### Production Configuration
```yaml
oracle:
  host: "${ORACLE_HOST}"
  port: "${ORACLE_PORT:1521}"
  service_name: "${ORACLE_SERVICE}"
  user: "${ORACLE_USER}"
  password: "${ORACLE_PASSWORD}"
  
  pool:
    min_connections: 5
    max_connections: 20
    timeout: 60
    retry_count: 5

aml:
  owners:
    - "AML_PROD"
    - "AML_STAGE"
    - "REFERENCE"
    - "LOOKUP"
  
  table_patterns:
    - ".*CUSTOMER.*"
    - ".*PARTY.*"
    - ".*ACCOUNT.*"
    - ".*TRANSACTION.*"
    - ".*ALERT.*"
    - ".*CASE.*"
    - ".*SANCTION.*"
    - ".*WATCHLIST.*"

catalog:
  path: "/data/indexes/graph/AML_PROD.sqlite"
  
graphs:
  export_dir: "/data/exports/graphs"
  
logging:
  level: "INFO"
  file: "/logs/aml_metadata.log"
```

### Schema Reference

#### Catalog Tables

**schemas**
```sql
CREATE TABLE schemas (
    owner TEXT PRIMARY KEY,
    default_tablespace TEXT,
    created TEXT,
    last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

**tables**
```sql
CREATE TABLE tables (
    owner TEXT NOT NULL,
    table_name TEXT NOT NULL,
    tablespace_name TEXT,
    num_rows INTEGER,
    last_analyzed TEXT,
    last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (owner, table_name)
);
```

**columns**
```sql
CREATE TABLE columns (
    owner TEXT NOT NULL,
    table_name TEXT NOT NULL,
    column_name TEXT NOT NULL,
    data_type TEXT,
    data_length INTEGER,
    nullable TEXT,
    is_pii BOOLEAN DEFAULT 0,
    last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (owner, table_name, column_name)
);
```

**relationships**
```sql
CREATE TABLE relationships (
    source_table TEXT NOT NULL,
    target_table TEXT NOT NULL,
    constraint_name TEXT,
    cardinality TEXT,
    quality REAL,
    column_mappings TEXT,  -- JSON
    last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (source_table, target_table, constraint_name)
);
```

### PII Classification Rules

Column name patterns automatically classified as PII:
- `.*SSN.*`, `.*SOCIAL.*` - Social Security Numbers
- `.*EMAIL.*`, `.*MAIL.*` - Email addresses  
- `.*PHONE.*`, `.*MOBILE.*` - Phone numbers
- `.*DOB.*`, `.*BIRTH.*` - Date of birth
- `.*FIRST.*NAME.*`, `.*LAST.*NAME.*` - Personal names
- `.*ADDRESS.*`, `.*ADDR.*` - Addresses
- `.*ACCOUNT.*NUM.*` - Account numbers
- `.*PASSPORT.*`, `.*DRIVER.*` - Identity documents

Data type patterns:
- `CLOB` columns containing text data
- `VARCHAR2` fields > 100 characters (potential free text)
- `DATE` columns with birth-related names

---

*This documentation covers the complete Oracle metadata support system for PIO-AI. For additional support or feature requests, please refer to the project repository.*