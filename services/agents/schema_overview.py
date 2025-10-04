"""
Holistic schema overview system with intelligent caching and on-demand retrieval.
Supports schema mapping, relationship graphs, and metadata enrichment.
"""

import logging
import sqlite3
import json
from typing import Dict, List, Optional, Any, Set, Tuple
from dataclasses import dataclass, field, asdict
from pathlib import Path
from datetime import datetime, timedelta
from collections import OrderedDict
import hashlib

logger = logging.getLogger(__name__)


@dataclass
class ColumnMetadata:
    """Complete column metadata."""
    name: str
    data_type: str
    nullable: bool
    primary_key: bool = False
    foreign_key: Optional[str] = None
    aml_required: bool = False
    sensitive: bool = False
    business_description: Optional[str] = None
    sample_values: List[Any] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class TableMetadata:
    """Complete table metadata."""
    name: str
    schema: str
    purpose: str
    columns: List[ColumnMetadata]
    primary_keys: List[str]
    foreign_keys: Dict[str, str]  # column -> referenced_table.column
    row_count: Optional[int] = None
    aml_related: bool = False
    compliance_required: bool = False
    last_updated: Optional[datetime] = None
    tags: List[str] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        if self.last_updated:
            d['last_updated'] = self.last_updated.isoformat()
        d['columns'] = [col.to_dict() for col in self.columns]
        return d
    
    @property
    def aml_column_count(self) -> int:
        """Count AML-required columns."""
        return sum(1 for col in self.columns if col.aml_required)
    
    @property
    def sensitive_column_count(self) -> int:
        """Count sensitive/PII columns."""
        return sum(1 for col in self.columns if col.sensitive)


@dataclass
class SchemaRelationship:
    """Relationship between tables."""
    from_table: str
    to_table: str
    from_column: str
    to_column: str
    relationship_type: str  # one-to-one, one-to-many, many-to-many
    confidence: float = 1.0


class TTLCache:
    """Time-to-live cache with automatic expiration."""
    
    def __init__(self, ttl_seconds: int = 300, max_size: int = 1000):
        """
        Initialize TTL cache.
        
        Args:
            ttl_seconds: Time to live in seconds
            max_size: Maximum cache size
        """
        self.ttl_seconds = ttl_seconds
        self.max_size = max_size
        self._cache: OrderedDict = OrderedDict()
        self._timestamps: Dict[str, datetime] = {}
        self._hits = 0
        self._misses = 0
    
    def get(self, key: str) -> Optional[Any]:
        """Get value from cache if not expired."""
        if key not in self._cache:
            self._misses += 1
            return None
        
        # Check expiration
        timestamp = self._timestamps[key]
        if datetime.now() - timestamp > timedelta(seconds=self.ttl_seconds):
            # Expired
            del self._cache[key]
            del self._timestamps[key]
            self._misses += 1
            return None
        
        # Move to end (LRU)
        self._cache.move_to_end(key)
        self._hits += 1
        return self._cache[key]
    
    def set(self, key: str, value: Any):
        """Set value in cache."""
        # Remove oldest if at capacity
        if len(self._cache) >= self.max_size:
            oldest_key = next(iter(self._cache))
            del self._cache[oldest_key]
            del self._timestamps[oldest_key]
        
        self._cache[key] = value
        self._timestamps[key] = datetime.now()
    
    def invalidate(self, key: str):
        """Invalidate specific cache entry."""
        if key in self._cache:
            del self._cache[key]
            del self._timestamps[key]
    
    def clear(self):
        """Clear entire cache."""
        self._cache.clear()
        self._timestamps.clear()
    
    def stats(self) -> Dict[str, Any]:
        """Get cache statistics."""
        total = self._hits + self._misses
        hit_rate = self._hits / total if total > 0 else 0
        
        return {
            "size": len(self._cache),
            "max_size": self.max_size,
            "hits": self._hits,
            "misses": self._misses,
            "hit_rate": hit_rate,
            "ttl_seconds": self.ttl_seconds
        }


class SchemaRepository:
    """Repository for schema metadata with caching."""
    
    def __init__(
        self,
        catalog_db_path: Path,
        graph_client: Optional[Any] = None,
        cache_ttl: int = 300
    ):
        """
        Initialize schema repository.
        
        Args:
            catalog_db_path: Path to catalog database
            graph_client: Neo4j graph client
            cache_ttl: Cache TTL in seconds
        """
        self.catalog_db_path = catalog_db_path
        self.graph_client = graph_client
        self.cache = TTLCache(ttl_seconds=cache_ttl)
        
        # In-memory indexes
        self.table_index: Dict[str, TableMetadata] = {}
        self.column_index: Dict[str, List[str]] = {}  # column_name -> [table_names]
        self.relationship_index: Dict[str, List[SchemaRelationship]] = {}
        
        # Load core metadata
        self._initialize()
        
        logger.info(
            "Schema repository initialized",
            extra={
                "operation": "schema_repo.init",
                "catalog_path": str(catalog_db_path),
                "has_graph": graph_client is not None,
                "cache_ttl": cache_ttl
            }
        )
    
    def _initialize(self):
        """Initialize schema indexes."""
        try:
            if not self.catalog_db_path.exists():
                logger.warning(f"Catalog database not found: {self.catalog_db_path}")
                return
            
            # Load table metadata
            self._load_table_metadata()
            
            # Load relationships
            self._load_relationships()
            
            logger.info(
                f"Schema repository loaded: {len(self.table_index)} tables, "
                f"{len(self.relationship_index)} relationships"
            )
        except Exception as e:
            logger.error(f"Failed to initialize schema repository: {e}")
    
    def _load_table_metadata(self):
        """Load table metadata from catalog."""
        try:
            conn = sqlite3.connect(self.catalog_db_path)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            
            # Get all tables
            cursor.execute("""
                SELECT DISTINCT table_name, table_schema, business_purpose
                FROM metadata
            """)
            
            for row in cursor.fetchall():
                table_name = row['table_name']
                
                # Get columns for this table
                columns = self._load_table_columns(cursor, table_name)
                
                # Create table metadata
                table_meta = TableMetadata(
                    name=table_name,
                    schema=row['table_schema'] or 'public',
                    purpose=row['business_purpose'] or 'No description available',
                    columns=columns,
                    primary_keys=[c.name for c in columns if c.primary_key],
                    foreign_keys={c.name: c.foreign_key for c in columns if c.foreign_key},
                    aml_related=any(c.aml_required for c in columns)
                )
                
                self.table_index[table_name] = table_meta
                
                # Build column index
                for col in columns:
                    if col.name not in self.column_index:
                        self.column_index[col.name] = []
                    self.column_index[col.name].append(table_name)
            
            conn.close()
            
        except Exception as e:
            logger.error(f"Failed to load table metadata: {e}")
    
    def _load_table_columns(
        self,
        cursor: sqlite3.Cursor,
        table_name: str
    ) -> List[ColumnMetadata]:
        """Load columns for a specific table."""
        cursor.execute("""
            SELECT column_name, data_type, is_nullable,
                   is_primary_key, foreign_key_ref,
                   aml_required, is_sensitive, column_description
            FROM metadata
            WHERE table_name = ?
        """, (table_name,))
        
        columns = []
        for row in cursor.fetchall():
            col = ColumnMetadata(
                name=row['column_name'],
                data_type=row['data_type'] or 'VARCHAR',
                nullable=row['is_nullable'] == 'YES',
                primary_key=row['is_primary_key'] == 1,
                foreign_key=row['foreign_key_ref'],
                aml_required=row['aml_required'] == 1,
                sensitive=row['is_sensitive'] == 1,
                business_description=row['column_description']
            )
            columns.append(col)
        
        return columns
    
    def _load_relationships(self):
        """Load relationships from graph or catalog."""
        if self.graph_client:
            self._load_relationships_from_graph()
        else:
            self._load_relationships_from_catalog()
    
    def _load_relationships_from_graph(self):
        """Load relationships from Neo4j graph."""
        try:
            query = """
            MATCH (t1:Table)-[r:RELATES_TO]->(t2:Table)
            RETURN t1.name as from_table, t2.name as to_table,
                   r.from_column as from_column, r.to_column as to_column,
                   r.type as rel_type
            """
            
            result = self.graph_client.run(query)
            
            for record in result:
                rel = SchemaRelationship(
                    from_table=record['from_table'],
                    to_table=record['to_table'],
                    from_column=record['from_column'],
                    to_column=record['to_column'],
                    relationship_type=record['rel_type'],
                    confidence=1.0
                )
                
                if rel.from_table not in self.relationship_index:
                    self.relationship_index[rel.from_table] = []
                self.relationship_index[rel.from_table].append(rel)
                
        except Exception as e:
            logger.error(f"Failed to load relationships from graph: {e}")
    
    def _load_relationships_from_catalog(self):
        """Load relationships from foreign key definitions."""
        for table_name, table_meta in self.table_index.items():
            for col_name, fk_ref in table_meta.foreign_keys.items():
                if '.' in fk_ref:
                    ref_table, ref_col = fk_ref.split('.', 1)
                    
                    rel = SchemaRelationship(
                        from_table=table_name,
                        to_table=ref_table,
                        from_column=col_name,
                        to_column=ref_col,
                        relationship_type='one-to-many',
                        confidence=1.0
                    )
                    
                    if table_name not in self.relationship_index:
                        self.relationship_index[table_name] = []
                    self.relationship_index[table_name].append(rel)
    
    def get_table(self, table_name: str) -> Optional[TableMetadata]:
        """
        Get table metadata with caching.
        
        Args:
            table_name: Name of table
            
        Returns:
            Table metadata or None
        """
        # Check cache
        cache_key = f"table:{table_name}"
        cached = self.cache.get(cache_key)
        if cached:
            return cached
        
        # Get from index
        table_meta = self.table_index.get(table_name)
        
        if table_meta:
            # Cache it
            self.cache.set(cache_key, table_meta)
        
        return table_meta
    
    def search_tables(
        self,
        query: str,
        filters: Optional[Dict[str, Any]] = None
    ) -> List[TableMetadata]:
        """
        Search for tables matching query.
        
        Args:
            query: Search query
            filters: Optional filters (aml_related, compliance_required, etc.)
            
        Returns:
            List of matching tables
        """
        query_lower = query.lower()
        matches = []
        
        for table_meta in self.table_index.values():
            # Check name match
            if query_lower in table_meta.name.lower():
                matches.append(table_meta)
                continue
            
            # Check purpose match
            if table_meta.purpose and query_lower in table_meta.purpose.lower():
                matches.append(table_meta)
                continue
            
            # Check tags
            if any(query_lower in tag.lower() for tag in table_meta.tags):
                matches.append(table_meta)
                continue
        
        # Apply filters
        if filters:
            if filters.get('aml_related'):
                matches = [t for t in matches if t.aml_related]
            if filters.get('compliance_required'):
                matches = [t for t in matches if t.compliance_required]
        
        return matches
    
    def search_columns(self, column_name: str) -> List[Tuple[str, ColumnMetadata]]:
        """
        Find all tables containing a column.
        
        Args:
            column_name: Name of column
            
        Returns:
            List of (table_name, column_metadata) tuples
        """
        results = []
        
        table_names = self.column_index.get(column_name, [])
        for table_name in table_names:
            table_meta = self.get_table(table_name)
            if table_meta:
                for col in table_meta.columns:
                    if col.name == column_name:
                        results.append((table_name, col))
        
        return results
    
    def get_relationships(
        self,
        table_name: str,
        direction: str = 'both'
    ) -> List[SchemaRelationship]:
        """
        Get relationships for a table.
        
        Args:
            table_name: Name of table
            direction: 'outgoing', 'incoming', or 'both'
            
        Returns:
            List of relationships
        """
        relationships = []
        
        # Outgoing relationships
        if direction in ('outgoing', 'both'):
            relationships.extend(self.relationship_index.get(table_name, []))
        
        # Incoming relationships
        if direction in ('incoming', 'both'):
            for rels in self.relationship_index.values():
                for rel in rels:
                    if rel.to_table == table_name:
                        relationships.append(rel)
        
        return relationships
    
    def get_schema_summary(self) -> str:
        """
        Generate high-level schema summary.
        
        Returns:
            Formatted summary text
        """
        cache_key = "schema:summary"
        cached = self.cache.get(cache_key)
        if cached:
            return cached
        
        # Build summary
        total_tables = len(self.table_index)
        aml_tables = sum(1 for t in self.table_index.values() if t.aml_related)
        
        # Group by common prefixes
        prefixes = {}
        for table_name in self.table_index.keys():
            if '_' in table_name:
                prefix = table_name.split('_')[0]
                prefixes[prefix] = prefixes.get(prefix, 0) + 1
        
        summary_parts = [
            f"Database Overview:",
            f"- Total Tables: {total_tables}",
            f"- AML-Related Tables: {aml_tables}",
            "",
            "Major Subject Areas:"
        ]
        
        for prefix, count in sorted(prefixes.items(), key=lambda x: x[1], reverse=True)[:5]:
            summary_parts.append(f"  - {prefix}: {count} tables")
        
        summary = "\n".join(summary_parts)
        
        # Cache summary
        self.cache.set(cache_key, summary)
        
        return summary
    
    def get_table_detail_for_llm(
        self,
        table_name: str,
        include_sample_columns: int = 8
    ) -> str:
        """
        Generate detailed table description for LLM context.
        
        Args:
            table_name: Name of table
            include_sample_columns: Number of columns to include
            
        Returns:
            Formatted description
        """
        table_meta = self.get_table(table_name)
        if not table_meta:
            return f"Table '{table_name}' not found in schema."
        
        parts = [
            f"Table: {table_meta.name}",
            f"Schema: {table_meta.schema}",
            f"Purpose: {table_meta.purpose}",
            f"Total Columns: {len(table_meta.columns)}",
            f"AML Required Columns: {table_meta.aml_column_count}",
            f"Sensitive/PII Columns: {table_meta.sensitive_column_count}",
            ""
        ]
        
        # Add primary keys
        if table_meta.primary_keys:
            parts.append(f"Primary Keys: {', '.join(table_meta.primary_keys)}")
        
        # Add relationships
        relationships = self.get_relationships(table_name)
        if relationships:
            parts.append(f"Related Tables: {len(relationships)}")
            for rel in relationships[:3]:
                parts.append(f"  - {rel.to_table} via {rel.from_column}")
        
        parts.append("")
        parts.append(f"Column Details (showing {min(include_sample_columns, len(table_meta.columns))}):")
        
        # Show columns (prioritize AML-required and sensitive)
        priority_cols = [c for c in table_meta.columns if c.aml_required or c.sensitive or c.primary_key]
        other_cols = [c for c in table_meta.columns if c not in priority_cols]
        
        cols_to_show = (priority_cols + other_cols)[:include_sample_columns]
        
        for col in cols_to_show:
            flags = []
            if col.primary_key:
                flags.append("PK")
            if col.aml_required:
                flags.append("AML")
            if col.sensitive:
                flags.append("Sensitive")
            
            flag_str = f" [{', '.join(flags)}]" if flags else ""
            desc = f" - {col.business_description}" if col.business_description else ""
            
            parts.append(f"  - {col.name} ({col.data_type}){flag_str}{desc}")
        
        return "\n".join(parts)
    
    def get_cache_stats(self) -> Dict[str, Any]:
        """Get cache statistics."""
        return self.cache.stats()


class SchemaOverviewBuilder:
    """Build comprehensive schema overviews for LLM prompting."""
    
    def __init__(self, schema_repo: SchemaRepository):
        """
        Initialize builder.
        
        Args:
            schema_repo: Schema repository
        """
        self.schema_repo = schema_repo
    
    def build_context_for_query(
        self,
        query: str,
        relevant_tables: List[str],
        max_detail_level: str = 'medium'
    ) -> str:
        """
        Build schema context for a specific query.
        
        Args:
            query: User query
            relevant_tables: List of relevant table names
            max_detail_level: 'low', 'medium', or 'high'
            
        Returns:
            Formatted schema context
        """
        if max_detail_level == 'low':
            return self._build_low_detail(relevant_tables)
        elif max_detail_level == 'high':
            return self._build_high_detail(relevant_tables)
        else:
            return self._build_medium_detail(relevant_tables)
    
    def _build_low_detail(self, tables: List[str]) -> str:
        """Build low-detail overview (just table names and purposes)."""
        parts = ["Relevant Tables:"]
        
        for table_name in tables[:10]:
            table_meta = self.schema_repo.get_table(table_name)
            if table_meta:
                parts.append(f"- {table_name}: {table_meta.purpose}")
        
        return "\n".join(parts)
    
    def _build_medium_detail(self, tables: List[str]) -> str:
        """Build medium-detail overview (key columns and relationships)."""
        parts = []
        
        for table_name in tables[:5]:
            detail = self.schema_repo.get_table_detail_for_llm(table_name, include_sample_columns=5)
            parts.append(detail)
            parts.append("")
        
        return "\n".join(parts)
    
    def _build_high_detail(self, tables: List[str]) -> str:
        """Build high-detail overview (all columns and full metadata)."""
        parts = []
        
        for table_name in tables[:3]:
            detail = self.schema_repo.get_table_detail_for_llm(table_name, include_sample_columns=20)
            parts.append(detail)
            parts.append("")
        
        return "\n".join(parts)
