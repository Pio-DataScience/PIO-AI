"""
Schema Retriever
BM25 + embedding search over database catalog with join path finding.
"""
import logging
import json
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass, asdict
import re

# Import existing retrieval components
from .hybrid import HybridRetriever
from ..db import CatalogStore, RelationshipBuilder
from ..indexer.bm25_index import BM25Index
from ..indexer.faiss_index import FAISSIndex

logger = logging.getLogger(__name__)

@dataclass
class SchemaEntity:
    """Represents a searchable schema entity."""
    entity_type: str  # 'table', 'column', 'view'
    owner: str
    name: str
    full_name: str  # e.g., "OWNER.TABLE.COLUMN"
    data_type: Optional[str] = None
    comments: Optional[str] = None
    table_name: Optional[str] = None  # For columns
    is_pii: bool = False
    metadata: Dict[str, Any] = None
    
    def __post_init__(self):
        if self.metadata is None:
            self.metadata = {}

@dataclass
class SchemaSearchResult:
    """Result from schema search."""
    entity: SchemaEntity
    relevance_score: float
    bm25_score: float
    embedding_score: float
    match_type: str  # 'exact', 'partial', 'semantic'

@dataclass
class JoinPathResult:
    """Result containing join path and synthetic SQL."""
    source_table: str
    target_table: str
    join_path: List[str]
    synthetic_sql: str
    relationships: List[Dict[str, Any]]
    quality_score: float
    citations: List[str]

class SchemaRetriever:
    """Retrieves schema information using BM25 + embeddings with join path finding."""
    
    def __init__(self, catalog_store: CatalogStore, bm25_index: BM25Index, 
                 faiss_index: FAISSIndex, relationship_builder: RelationshipBuilder):
        self.catalog = catalog_store
        self.bm25_index = bm25_index
        self.faiss_index = faiss_index
        self.relationship_builder = relationship_builder
        
        # Cache for schema entities
        self._schema_entities = None
        self._entities_by_name = None
        
    def _load_schema_entities(self) -> List[SchemaEntity]:
        """Load and cache schema entities from catalog."""
        if self._schema_entities is not None:
            return self._schema_entities
        
        logger.info("Loading schema entities from catalog")
        entities = []
        
        catalog_entities = self.catalog.get_catalog_entities_for_search()
        
        for entity_data in catalog_entities:
            entity_type = entity_data['entity_type']
            owner = entity_data['owner']
            
            if entity_type == 'table':
                table_name = entity_data['table_name']
                entity = SchemaEntity(
                    entity_type='table',
                    owner=owner,
                    name=table_name,
                    full_name=f"{owner}.{table_name}",
                    comments=entity_data.get('comments'),
                    metadata={'num_rows': entity_data.get('num_rows')}
                )
                
            elif entity_type == 'column':
                table_name = entity_data['table_name']
                column_name = entity_data['column_name']
                entity = SchemaEntity(
                    entity_type='column',
                    owner=owner,
                    name=column_name,
                    full_name=f"{owner}.{table_name}.{column_name}",
                    table_name=table_name,
                    data_type=entity_data.get('data_type'),
                    comments=entity_data.get('comments'),
                    is_pii=entity_data.get('is_pii', False)
                )
                
            elif entity_type == 'view':
                view_name = entity_data['view_name']
                entity = SchemaEntity(
                    entity_type='view',
                    owner=owner,
                    name=view_name,
                    full_name=f"{owner}.{view_name}",
                    comments=entity_data.get('comments')
                )
            
            else:
                continue
            
            entities.append(entity)
        
        self._schema_entities = entities
        
        # Build name index for quick lookups
        self._entities_by_name = {}
        for entity in entities:
            name_key = entity.full_name.upper()
            if name_key not in self._entities_by_name:
                self._entities_by_name[name_key] = []
            self._entities_by_name[name_key].append(entity)
            
            # Also index by just the object name
            simple_name = entity.name.upper()
            if simple_name not in self._entities_by_name:
                self._entities_by_name[simple_name] = []
            self._entities_by_name[simple_name].append(entity)
        
        logger.info(f"Loaded {len(entities)} schema entities")
        return entities
    
    def _create_searchable_text(self, entity: SchemaEntity) -> str:
        """Create searchable text for an entity."""
        text_parts = [
            entity.full_name,
            entity.name,
            entity.owner
        ]
        
        if entity.table_name:
            text_parts.append(entity.table_name)
        
        if entity.data_type:
            text_parts.append(entity.data_type)
        
        if entity.comments:
            text_parts.append(entity.comments)
        
        # Add some semantic context
        if entity.entity_type == 'table':
            text_parts.append("database table")
        elif entity.entity_type == 'column':
            text_parts.append("database column field")
        elif entity.entity_type == 'view':
            text_parts.append("database view")
        
        return " ".join(filter(None, text_parts))
    
    def search_schema(self, query: str, limit: int = 20, 
                     entity_types: Optional[List[str]] = None) -> List[SchemaSearchResult]:
        """
        Search schema entities using hybrid BM25 + embedding approach.
        
        Args:
            query: Search query
            limit: Maximum number of results
            entity_types: Filter by entity types ('table', 'column', 'view')
            
        Returns:
            List of schema search results
        """
        entities = self._load_schema_entities()
        
        # Filter by entity types if specified
        if entity_types:
            entities = [e for e in entities if e.entity_type in entity_types]
        
        if not entities:
            return []
        
        # Create searchable texts
        searchable_texts = [self._create_searchable_text(entity) for entity in entities]
        
        # Perform hybrid search (if indexes are available)
        try:
            # Use BM25 for keyword matching
            bm25_scores = self._search_bm25(query, searchable_texts)
            
            # Use embeddings for semantic matching
            embedding_scores = self._search_embeddings(query, searchable_texts)
            
            # Combine scores
            results = []
            for i, entity in enumerate(entities):
                bm25_score = bm25_scores.get(i, 0.0)
                embedding_score = embedding_scores.get(i, 0.0)
                
                # Weighted combination (favor BM25 for exact matches)
                combined_score = 0.6 * bm25_score + 0.4 * embedding_score
                
                # Determine match type
                match_type = self._determine_match_type(query, entity, bm25_score, embedding_score)
                
                if combined_score > 0.1:  # Minimum relevance threshold
                    result = SchemaSearchResult(
                        entity=entity,
                        relevance_score=combined_score,
                        bm25_score=bm25_score,
                        embedding_score=embedding_score,
                        match_type=match_type
                    )
                    results.append(result)
            
            # Sort by relevance and limit
            results.sort(key=lambda x: x.relevance_score, reverse=True)
            return results[:limit]
            
        except Exception as e:
            logger.error(f"Error in schema search: {e}")
            # Fallback to simple text matching
            return self._fallback_text_search(query, entities, limit)
    
    def _search_bm25(self, query: str, texts: List[str]) -> Dict[int, float]:
        """Search using BM25 index."""
        # Simple BM25-like scoring for now
        # In production, integrate with actual BM25Index
        scores = {}
        query_terms = query.lower().split()
        
        for i, text in enumerate(texts):
            text_lower = text.lower()
            score = 0.0
            
            for term in query_terms:
                if term in text_lower:
                    # Simple term frequency
                    tf = text_lower.count(term)
                    score += tf * 0.1
            
            if score > 0:
                scores[i] = min(score, 1.0)
        
        return scores
    
    def _search_embeddings(self, query: str, texts: List[str]) -> Dict[int, float]:
        """Search using embedding similarity."""
        # Placeholder for embedding search
        # In production, integrate with actual FAISSIndex
        scores = {}
        
        # Simple semantic matching for demonstration
        query_lower = query.lower()
        for i, text in enumerate(texts):
            text_lower = text.lower()
            
            # Simple semantic scoring based on word overlap
            query_words = set(query_lower.split())
            text_words = set(text_lower.split())
            
            if query_words and text_words:
                overlap = len(query_words.intersection(text_words))
                union = len(query_words.union(text_words))
                similarity = overlap / union if union > 0 else 0
                
                if similarity > 0.1:
                    scores[i] = similarity
        
        return scores
    
    def _determine_match_type(self, query: str, entity: SchemaEntity, 
                            bm25_score: float, embedding_score: float) -> str:
        """Determine the type of match."""
        query_lower = query.lower()
        entity_name_lower = entity.name.lower()
        full_name_lower = entity.full_name.lower()
        
        if query_lower == entity_name_lower or query_lower == full_name_lower:
            return 'exact'
        elif query_lower in entity_name_lower or query_lower in full_name_lower:
            return 'partial'
        elif bm25_score > 0.5:
            return 'keyword'
        else:
            return 'semantic'
    
    def _fallback_text_search(self, query: str, entities: List[SchemaEntity], 
                            limit: int) -> List[SchemaSearchResult]:
        """Fallback text search when indexes are not available."""
        results = []
        query_lower = query.lower()
        
        for entity in entities:
            searchable_text = self._create_searchable_text(entity).lower()
            
            # Simple scoring based on term presence and position
            score = 0.0
            
            if query_lower == entity.name.lower():
                score = 1.0
            elif query_lower in entity.name.lower():
                score = 0.8
            elif query_lower in entity.full_name.lower():
                score = 0.6
            elif query_lower in searchable_text:
                score = 0.4
            
            if score > 0:
                result = SchemaSearchResult(
                    entity=entity,
                    relevance_score=score,
                    bm25_score=score,
                    embedding_score=0.0,
                    match_type='partial' if score < 1.0 else 'exact'
                )
                results.append(result)
        
        results.sort(key=lambda x: x.relevance_score, reverse=True)
        return results[:limit]
    
    def find_join_path(self, table1: str, table2: str) -> Optional[JoinPathResult]:
        """
        Find join path between two tables and generate synthetic SQL.
        
        Args:
            table1: First table (can be OWNER.TABLE or just TABLE)
            table2: Second table (can be OWNER.TABLE or just TABLE)
            
        Returns:
            JoinPathResult with path and synthetic SQL
        """
        # Normalize table names
        table1_full = self._normalize_table_name(table1)
        table2_full = self._normalize_table_name(table2)
        
        if not table1_full or not table2_full:
            return None
        
        # Find join path using relationship builder
        join_path = self.relationship_builder.find_join_path(table1_full, table2_full)
        
        if not join_path:
            return None
        
        # Generate synthetic SQL
        synthetic_sql = self._generate_synthetic_sql(join_path)
        
        # Build citations
        citations = self._build_citations(join_path)
        
        # Convert relationships to dictionaries
        relationships_data = []
        for rel in join_path.relationships:
            rel_data = asdict(rel)
            relationships_data.append(rel_data)
        
        return JoinPathResult(
            source_table=table1_full,
            target_table=table2_full,
            join_path=join_path.path_nodes,
            synthetic_sql=synthetic_sql,
            relationships=relationships_data,
            quality_score=join_path.total_quality,
            citations=citations
        )
    
    def _normalize_table_name(self, table_name: str) -> Optional[str]:
        """Normalize table name to OWNER.TABLE format."""
        if not table_name:
            return None
        
        table_name = table_name.strip().upper()
        
        # If already in OWNER.TABLE format
        if '.' in table_name:
            return table_name
        
        # Search for table by name
        entities = self._load_schema_entities()
        
        for entity in entities:
            if entity.entity_type == 'table' and entity.name.upper() == table_name:
                return entity.full_name
        
        return None
    
    def _generate_synthetic_sql(self, join_path) -> str:
        """Generate synthetic SQL for join path."""
        if not join_path.relationships:
            return ""
        
        # Start with SELECT and FROM
        tables = join_path.path_nodes
        main_table = tables[0]
        
        # Build SELECT clause (select a few columns from each table)
        select_parts = []
        for table in tables:
            table_alias = self._get_table_alias(table)
            select_parts.append(f"{table_alias}.*")  # Simplified
        
        sql_parts = [
            f"SELECT {', '.join(select_parts[:3])}",  # Limit columns
            f"FROM {main_table} {self._get_table_alias(main_table)}"
        ]
        
        # Build JOIN clauses
        for i, relationship in enumerate(join_path.relationships):
            if i == 0:
                left_table = f"{relationship.fk_owner}.{relationship.fk_table}"
                right_table = f"{relationship.pk_owner}.{relationship.pk_table}"
            else:
                # Determine the correct table order based on the path
                if f"{relationship.fk_owner}.{relationship.fk_table}" in tables[:i+1]:
                    left_table = f"{relationship.fk_owner}.{relationship.fk_table}"
                    right_table = f"{relationship.pk_owner}.{relationship.pk_table}"
                else:
                    left_table = f"{relationship.pk_owner}.{relationship.pk_table}"
                    right_table = f"{relationship.fk_owner}.{relationship.fk_table}"
            
            left_alias = self._get_table_alias(left_table)
            right_alias = self._get_table_alias(right_table)
            
            # Build JOIN condition from column mappings
            join_conditions = []
            for mapping in relationship.column_mappings:
                if relationship.fk_owner == left_table.split('.')[0]:
                    fk_col = f"{left_alias}.{mapping.fk_column}"
                    pk_col = f"{right_alias}.{mapping.pk_column}"
                else:
                    fk_col = f"{right_alias}.{mapping.fk_column}"
                    pk_col = f"{left_alias}.{mapping.pk_column}"
                
                join_conditions.append(f"{fk_col} = {pk_col}")
            
            join_condition = " AND ".join(join_conditions)
            sql_parts.append(f"JOIN {right_table} {right_alias} ON {join_condition}")
        
        return "\n".join(sql_parts)
    
    def _get_table_alias(self, table_name: str) -> str:
        """Generate table alias from table name."""
        if '.' in table_name:
            owner, table = table_name.split('.')
            return table[:3].lower()  # First 3 characters
        return table_name[:3].lower()
    
    def _build_citations(self, join_path) -> List[str]:
        """Build citations for join path."""
        citations = []
        
        for relationship in join_path.relationships:
            citation = (
                f"FK: {relationship.fk_owner}.{relationship.fk_table}.{relationship.fk_constraint} "
                f"-> PK: {relationship.pk_owner}.{relationship.pk_table}.{relationship.pk_constraint}"
            )
            citations.append(citation)
        
        return citations
    
    def explain_table(self, table_name: str) -> Dict[str, Any]:
        """
        Provide detailed explanation of a table.
        
        Args:
            table_name: Table name to explain
            
        Returns:
            Dictionary with table details
        """
        table_full = self._normalize_table_name(table_name)
        if not table_full:
            return {"error": f"Table '{table_name}' not found"}
        
        owner, table = table_full.split('.')
        
        # Get table details
        tables = self.catalog.get_tables_for_owner(owner)
        table_info = next((t for t in tables if t['table_name'] == table), None)
        
        if not table_info:
            return {"error": f"Table '{table_name}' not found"}
        
        # Get columns
        with self.catalog._get_connection() as conn:
            cursor = conn.execute("""
                SELECT column_name, data_type, nullable, is_pii
                FROM columns
                WHERE owner = ? AND table_name = ?
                ORDER BY column_name
            """, (owner, table))
            columns = [dict(row) for row in cursor.fetchall()]
            
            # Get relationships
            relationships = self.relationship_builder.get_table_relationships(owner, table)
            
            # Get comments
            cursor = conn.execute("""
                SELECT comments FROM table_comments
                WHERE owner = ? AND table_name = ?
            """, (owner, table))
            comment_row = cursor.fetchone()
            table_comment = comment_row['comments'] if comment_row else None
        
        return {
            "table": table_full,
            "owner": owner,
            "num_rows": table_info.get('num_rows'),
            "last_analyzed": table_info.get('last_analyzed'),
            "comment": table_comment,
            "columns": columns,
            "incoming_relationships": len(relationships["incoming"]),
            "outgoing_relationships": len(relationships["outgoing"]),
            "relationship_details": {
                "incoming": [asdict(rel) for rel in relationships["incoming"]],
                "outgoing": [asdict(rel) for rel in relationships["outgoing"]]
            }
        }
    
    def health_check(self) -> Dict[str, Any]:
        """Perform health check on schema retriever."""
        try:
            entities = self._load_schema_entities()
            
            return {
                "status": "healthy",
                "schema_entities": len(entities),
                "entities_by_type": {
                    "tables": len([e for e in entities if e.entity_type == 'table']),
                    "columns": len([e for e in entities if e.entity_type == 'column']),
                    "views": len([e for e in entities if e.entity_type == 'view'])
                },
                "graph_stats": {
                    "nodes": self.relationship_builder.graph.number_of_nodes(),
                    "edges": self.relationship_builder.graph.number_of_edges()
                }
            }
        except Exception as e:
            return {
                "status": "unhealthy",
                "error": str(e)
            }