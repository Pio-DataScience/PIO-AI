"""
Auto-traversal system for comprehensive query expansion and context gathering.
Implements hybrid search with BM25, embeddings, and graph-based relationship discovery.
"""

import logging
import re
from typing import Dict, List, Optional, Any, Set, Tuple
from dataclasses import dataclass, field
from pathlib import Path
import json

logger = logging.getLogger(__name__)


@dataclass
class EntityReference:
    """Extracted entity from query."""
    text: str
    entity_type: str  # TABLE, COLUMN, BUSINESS_TERM, TECHNICAL_TERM
    confidence: float
    context: str = ""
    
    
@dataclass
class SchemaNode:
    """Node in schema graph."""
    node_id: str
    node_type: str  # TABLE, COLUMN, RELATIONSHIP
    name: str
    metadata: Dict[str, Any] = field(default_factory=dict)
    connections: List[str] = field(default_factory=list)
    relevance_score: float = 0.0


@dataclass
class JoinPath:
    """Represents a join path between tables."""
    source_table: str
    target_table: str
    path: List[Tuple[str, str, str]]  # [(table, column, relationship_type)]
    distance: int
    confidence: float


class EntityExtractor:
    """Extract entities and references from queries."""
    
    # Patterns for entity detection
    TABLE_PATTERNS = [
        r'\b(PIO_[A-Z_]+)\b',  # PIO_ prefix
        r'\b([A-Z][A-Z_]+)\b',  # All caps words
        r'\b([a-z]+\.[a-z_]+)\b',  # dot notation
    ]
    
    BUSINESS_TERMS = {
        'customer', 'client', 'account', 'transaction', 'alert', 'aml',
        'kyc', 'risk', 'compliance', 'monitoring', 'report', 'entity',
        'suspicious', 'activity', 'screening', 'sanctions', 'pep'
    }
    
    TECHNICAL_TERMS = {
        'schema', 'table', 'column', 'field', 'database', 'query',
        'join', 'relationship', 'foreign key', 'primary key', 'index'
    }
    
    def __init__(self):
        """Initialize entity extractor."""
        self.compiled_patterns = [re.compile(p, re.IGNORECASE) for p in self.TABLE_PATTERNS]
    
    def extract_entities(self, query: str) -> List[EntityReference]:
        """
        Extract all entities from query.
        
        Args:
            query: User query
            
        Returns:
            List of extracted entities
        """
        entities = []
        query_lower = query.lower()
        
        # Extract table-like references
        for pattern in self.compiled_patterns:
            for match in pattern.finditer(query):
                entity = match.group(1)
                entities.append(EntityReference(
                    text=entity,
                    entity_type="TABLE",
                    confidence=0.8,
                    context=query[max(0, match.start()-20):min(len(query), match.end()+20)]
                ))
        
        # Extract business terms
        words = query_lower.split()
        for i, word in enumerate(words):
            clean_word = re.sub(r'[^\w]', '', word)
            if clean_word in self.BUSINESS_TERMS:
                entities.append(EntityReference(
                    text=clean_word,
                    entity_type="BUSINESS_TERM",
                    confidence=0.9,
                    context=' '.join(words[max(0, i-3):min(len(words), i+4)])
                ))
        
        # Extract technical terms
        for term in self.TECHNICAL_TERMS:
            if term in query_lower:
                entities.append(EntityReference(
                    text=term,
                    entity_type="TECHNICAL_TERM",
                    confidence=0.7,
                    context=query_lower
                ))
        
        # Deduplicate by text
        seen = set()
        unique_entities = []
        for entity in entities:
            if entity.text.lower() not in seen:
                seen.add(entity.text.lower())
                unique_entities.append(entity)
        
        logger.info(
            f"Extracted {len(unique_entities)} entities from query",
            extra={
                "operation": "entity_extraction",
                "entity_count": len(unique_entities),
                "entity_types": {e.entity_type for e in unique_entities}
            }
        )
        
        return unique_entities


class HybridSchemaSearch:
    """
    Hybrid search combining BM25, embeddings, and graph traversal.
    """
    
    def __init__(
        self,
        bm25_retriever: Optional[Any] = None,
        vector_retriever: Optional[Any] = None,
        graph_client: Optional[Any] = None,
        catalog_db_path: Optional[Path] = None
    ):
        """
        Initialize hybrid search.
        
        Args:
            bm25_retriever: BM25 keyword search
            vector_retriever: Embedding-based search
            graph_client: Graph database client (Neo4j)
            catalog_db_path: Path to catalog database
        """
        self.bm25_retriever = bm25_retriever
        self.vector_retriever = vector_retriever
        self.graph_client = graph_client
        self.catalog_db_path = catalog_db_path
        
        # Cache for schema lookups
        self._schema_cache: Dict[str, Any] = {}
        
        logger.info(
            "Hybrid search initialized",
            extra={
                "operation": "hybrid_search.init",
                "has_bm25": bm25_retriever is not None,
                "has_vector": vector_retriever is not None,
                "has_graph": graph_client is not None
            }
        )
    
    def hybrid_search(
        self,
        query: str,
        entities: List[EntityReference],
        max_results: int = 20,
        use_graph: bool = True
    ) -> List[SchemaNode]:
        """
        Perform hybrid search combining multiple retrieval methods.
        
        Args:
            query: Search query
            entities: Extracted entities
            max_results: Maximum results to return
            use_graph: Whether to use graph expansion
            
        Returns:
            List of relevant schema nodes
        """
        all_nodes = {}
        
        # 1. BM25 keyword search
        if self.bm25_retriever:
            bm25_results = self._bm25_search(query, entities)
            for node in bm25_results:
                all_nodes[node.node_id] = node
        
        # 2. Vector semantic search
        if self.vector_retriever:
            vector_results = self._vector_search(query, max_results // 2)
            for node in vector_results:
                if node.node_id in all_nodes:
                    # Boost score if found by multiple methods
                    all_nodes[node.node_id].relevance_score += node.relevance_score * 0.5
                else:
                    all_nodes[node.node_id] = node
        
        # 3. Graph-based expansion
        if use_graph and self.graph_client and all_nodes:
            graph_results = self._graph_expansion(list(all_nodes.values()))
            for node in graph_results:
                if node.node_id not in all_nodes:
                    all_nodes[node.node_id] = node
        
        # Rank and return top results
        ranked_nodes = sorted(
            all_nodes.values(),
            key=lambda n: n.relevance_score,
            reverse=True
        )
        
        logger.info(
            f"Hybrid search found {len(ranked_nodes)} nodes",
            extra={
                "operation": "hybrid_search.complete",
                "query": query[:100],
                "total_nodes": len(ranked_nodes),
                "top_score": ranked_nodes[0].relevance_score if ranked_nodes else 0
            }
        )
        
        return ranked_nodes[:max_results]
    
    def _bm25_search(self, query: str, entities: List[EntityReference]) -> List[SchemaNode]:
        """
        BM25 keyword-based search.
        
        Args:
            query: Search query
            entities: Extracted entities
            
        Returns:
            List of schema nodes
        """
        nodes = []
        
        try:
            # Search for each entity
            for entity in entities:
                results = self.bm25_retriever.search(entity.text, k=10)
                for result in results:
                    node = SchemaNode(
                        node_id=result.get('id', result.get('name', '')),
                        node_type=result.get('type', 'UNKNOWN'),
                        name=result.get('name', entity.text),
                        metadata=result,
                        relevance_score=result.get('score', 0.5) * entity.confidence
                    )
                    nodes.append(node)
            
            # Also search the full query
            full_results = self.bm25_retriever.search(query, k=15)
            for result in full_results:
                node = SchemaNode(
                    node_id=result.get('id', result.get('name', '')),
                    node_type=result.get('type', 'UNKNOWN'),
                    name=result.get('name', ''),
                    metadata=result,
                    relevance_score=result.get('score', 0.5)
                )
                nodes.append(node)
                
        except Exception as e:
            logger.warning(f"BM25 search failed: {e}")
        
        return nodes
    
    def _vector_search(self, query: str, max_results: int) -> List[SchemaNode]:
        """
        Vector embedding-based semantic search.
        
        Args:
            query: Search query
            max_results: Maximum results
            
        Returns:
            List of schema nodes
        """
        nodes = []
        
        try:
            results = self.vector_retriever.semantic_search(query, max_results=max_results)
            
            for result in results:
                node = SchemaNode(
                    node_id=result.get('id', result.get('metadata', {}).get('name', '')),
                    node_type=result.get('metadata', {}).get('type', 'UNKNOWN'),
                    name=result.get('metadata', {}).get('name', ''),
                    metadata=result.get('metadata', {}),
                    relevance_score=result.get('distance', 0.5)
                )
                nodes.append(node)
                
        except Exception as e:
            logger.warning(f"Vector search failed: {e}")
        
        return nodes
    
    def _graph_expansion(self, seed_nodes: List[SchemaNode]) -> List[SchemaNode]:
        """
        Expand results using graph relationships.
        
        Args:
            seed_nodes: Initial nodes to expand from
            
        Returns:
            Additional related nodes
        """
        expanded_nodes = []
        
        if not self.graph_client:
            return expanded_nodes
        
        try:
            # For each seed node, find connected nodes
            for seed in seed_nodes[:5]:  # Limit expansion
                # Query graph for relationships
                related = self._query_graph_neighbors(seed.name)
                
                for rel_node in related:
                    schema_node = SchemaNode(
                        node_id=rel_node['id'],
                        node_type=rel_node['type'],
                        name=rel_node['name'],
                        metadata=rel_node,
                        connections=[seed.node_id],
                        relevance_score=seed.relevance_score * 0.6  # Propagate score with decay
                    )
                    expanded_nodes.append(schema_node)
                    
        except Exception as e:
            logger.warning(f"Graph expansion failed: {e}")
        
        return expanded_nodes
    
    def _query_graph_neighbors(self, node_name: str) -> List[Dict[str, Any]]:
        """
        Query graph database for neighboring nodes.
        
        Args:
            node_name: Name of the node
            
        Returns:
            List of neighbor nodes
        """
        if not self.graph_client:
            return []
        
        try:
            # Neo4j Cypher query
            query = """
            MATCH (n)-[r]-(neighbor)
            WHERE n.name = $name
            RETURN neighbor.id as id, neighbor.type as type, 
                   neighbor.name as name, type(r) as relationship
            LIMIT 20
            """
            
            result = self.graph_client.run(query, name=node_name)
            return list(result)
            
        except Exception as e:
            logger.error(f"Graph query failed: {e}")
            return []
    
    def find_join_paths(
        self,
        source_table: str,
        target_table: str,
        max_depth: int = 3
    ) -> List[JoinPath]:
        """
        Find join paths between two tables using graph.
        
        Args:
            source_table: Source table name
            target_table: Target table name
            max_depth: Maximum path length
            
        Returns:
            List of possible join paths
        """
        if not self.graph_client:
            logger.warning("Graph client not available for join path discovery")
            return []
        
        try:
            # Use graph shortest path algorithm
            query = """
            MATCH path = shortestPath(
                (source:Table {name: $source})-[*..{max_depth}]-(target:Table {name: $target})
            )
            RETURN path
            LIMIT 5
            """.replace('{max_depth}', str(max_depth))
            
            result = self.graph_client.run(query, source=source_table, target=target_table)
            
            join_paths = []
            for record in result:
                path = record['path']
                join_path = self._parse_graph_path(path, source_table, target_table)
                if join_path:
                    join_paths.append(join_path)
            
            logger.info(
                f"Found {len(join_paths)} join paths from {source_table} to {target_table}",
                extra={
                    "operation": "find_join_paths",
                    "source": source_table,
                    "target": target_table,
                    "paths_found": len(join_paths)
                }
            )
            
            return join_paths
            
        except Exception as e:
            logger.error(f"Failed to find join paths: {e}")
            return []
    
    def _parse_graph_path(
        self,
        graph_path: Any,
        source: str,
        target: str
    ) -> Optional[JoinPath]:
        """
        Parse graph path into JoinPath object.
        
        Args:
            graph_path: Graph database path object
            source: Source table
            target: Target table
            
        Returns:
            Parsed JoinPath or None
        """
        try:
            # Extract nodes and relationships from path
            path_elements = []
            nodes = graph_path.nodes
            relationships = graph_path.relationships
            
            for i, rel in enumerate(relationships):
                from_node = nodes[i]
                to_node = nodes[i + 1]
                path_elements.append((
                    from_node.get('name', ''),
                    rel.get('column', ''),
                    rel.type
                ))
            
            return JoinPath(
                source_table=source,
                target_table=target,
                path=path_elements,
                distance=len(path_elements),
                confidence=1.0 / (1 + len(path_elements))  # Shorter paths = higher confidence
            )
            
        except Exception as e:
            logger.warning(f"Failed to parse graph path: {e}")
            return None


class AutoTraversalEngine:
    """
    Main auto-traversal engine for query expansion and context gathering.
    """
    
    def __init__(
        self,
        hybrid_search: HybridSchemaSearch,
        entity_extractor: Optional[EntityExtractor] = None
    ):
        """
        Initialize auto-traversal engine.
        
        Args:
            hybrid_search: Hybrid search system
            entity_extractor: Entity extraction system
        """
        self.hybrid_search = hybrid_search
        self.entity_extractor = entity_extractor or EntityExtractor()
        
        # Context carryover for follow-up questions
        self.recent_entities: List[EntityReference] = []
        self.recent_tables: List[str] = []
        
        logger.info("Auto-traversal engine initialized")
    
    def expand_query(
        self,
        query: str,
        context: Optional[Dict[str, Any]] = None,
        is_followup: bool = False
    ) -> Dict[str, Any]:
        """
        Automatically expand and traverse query for comprehensive context.
        
        Args:
            query: User query
            context: Previous context (for follow-ups)
            is_followup: Whether this is a follow-up question
            
        Returns:
            Expanded context with all relevant schema information
        """
        # Extract entities from query
        entities = self.entity_extractor.extract_entities(query)
        
        # Add context from previous queries if follow-up
        if is_followup and context:
            entities.extend(self.recent_entities[:3])  # Last 3 entities
        
        # Perform hybrid search
        schema_nodes = self.hybrid_search.hybrid_search(
            query=query,
            entities=entities,
            max_results=30,
            use_graph=True
        )
        
        # Group nodes by type
        tables = [n for n in schema_nodes if n.node_type == 'TABLE']
        columns = [n for n in schema_nodes if n.node_type == 'COLUMN']
        
        # Find join paths between identified tables
        join_paths = []
        if len(tables) > 1:
            for i in range(len(tables) - 1):
                paths = self.hybrid_search.find_join_paths(
                    tables[i].name,
                    tables[i + 1].name
                )
                join_paths.extend(paths)
        
        # Build comprehensive context
        expanded_context = {
            "original_query": query,
            "extracted_entities": [
                {"text": e.text, "type": e.entity_type, "confidence": e.confidence}
                for e in entities
            ],
            "relevant_tables": [
                {
                    "name": t.name,
                    "metadata": t.metadata,
                    "relevance": t.relevance_score
                }
                for t in tables[:10]
            ],
            "relevant_columns": [
                {
                    "name": c.name,
                    "metadata": c.metadata,
                    "relevance": c.relevance_score
                }
                for c in columns[:20]
            ],
            "join_paths": [
                {
                    "from": jp.source_table,
                    "to": jp.target_table,
                    "path": jp.path,
                    "distance": jp.distance
                }
                for jp in join_paths
            ],
            "schema_nodes": schema_nodes
        }
        
        # Update recent context for follow-ups
        self.recent_entities = entities
        self.recent_tables = [t.name for t in tables]
        
        logger.info(
            "Query expansion complete",
            extra={
                "operation": "auto_traversal.expand_query",
                "query": query[:100],
                "entities_found": len(entities),
                "tables_found": len(tables),
                "columns_found": len(columns),
                "join_paths_found": len(join_paths)
            }
        )
        
        return expanded_context
    
    def get_holistic_schema_view(self, entities: List[str]) -> str:
        """
        Generate holistic schema description for LLM context.
        
        Args:
            entities: List of entity names
            
        Returns:
            Formatted schema description
        """
        # Search for each entity
        all_nodes = []
        for entity in entities:
            nodes = self.hybrid_search.hybrid_search(
                query=entity,
                entities=[EntityReference(text=entity, entity_type="UNKNOWN", confidence=1.0)],
                max_results=5,
                use_graph=False
            )
            all_nodes.extend(nodes)
        
        # Format as text
        description_parts = []
        
        tables = [n for n in all_nodes if n.node_type == 'TABLE']
        if tables:
            description_parts.append("Relevant Tables:")
            for table in tables[:5]:
                purpose = table.metadata.get('business_purpose', 'N/A')
                col_count = table.metadata.get('column_count', '?')
                aml_cols = table.metadata.get('aml_required_count', '?')
                
                description_parts.append(
                    f"  - {table.name}: {purpose} "
                    f"({col_count} columns, {aml_cols} AML-required)"
                )
        
        return "\n".join(description_parts)
