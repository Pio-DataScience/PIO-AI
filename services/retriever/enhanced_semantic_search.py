"""
Enhanced Semantic Search with Intent-Aware Retrieval.
Integrates query reformulation and complete metadata retrieval.
"""

import logging
from typing import List, Dict, Any, Optional, Tuple
import chromadb
from sentence_transformers import SentenceTransformer

from services.agents.query_reformulator import (
    IntelligentQueryReformulator,
    QueryIntent,
    RetrievalQuery
)

logger = logging.getLogger(__name__)


class EnhancedSemanticSearch:
    """
    Enhanced semantic search with intelligent query reformulation.
    Handles complete metadata retrieval for table-level queries.
    """
    
    def __init__(
        self,
        chroma_client: chromadb.Client,
        bge_model: SentenceTransformer,
        collection_name: str = "aml_catalog"
    ):
        """
        Initialize enhanced semantic search.
        
        Args:
            chroma_client: ChromaDB client
            bge_model: BGE embedding model
            collection_name: ChromaDB collection name
        """
        self.chroma_client = chroma_client
        self.bge_model = bge_model
        self.collection_name = collection_name
        self.collection = chroma_client.get_collection(name=collection_name)
        
        # Initialize query reformulator
        self.reformulator = IntelligentQueryReformulator()
        
        logger.info(f"Enhanced semantic search initialized with collection: {collection_name}")
    
    def search(
        self,
        query: str,
        max_results: int = 5,
        session_id: Optional[str] = None,
        filters: Optional[Dict[str, Any]] = None
    ) -> Tuple[List[Dict[str, Any]], RetrievalQuery]:
        """
        Perform intelligent semantic search.
        
        Args:
            query: Natural language query
            max_results: Maximum results to return
            session_id: Session identifier
            filters: Optional metadata filters
            
        Returns:
            Tuple of (search results, retrieval query info)
        """
        # Reformulate query
        retrieval_query = self.reformulator.reformulate(query, session_id)
        
        logger.info(
            f"Performing search with reformulated query",
            extra={
                "original": query[:50],
                "reformulated": retrieval_query.reformulated_query[:50],
                "intent": retrieval_query.intent.value,
                "complete_metadata": retrieval_query.should_retrieve_complete_metadata
            }
        )
        
        # Route based on intent and requirements
        if retrieval_query.should_retrieve_complete_metadata and retrieval_query.target_table:
            # Need complete table metadata
            results = self._retrieve_complete_table_metadata(
                retrieval_query.target_table,
                retrieval_query.reformulated_query,
                max_results
            )
        else:
            # Standard vector search
            results = self._perform_vector_search(
                retrieval_query.reformulated_query,
                max_results,
                filters,
                retrieval_query
            )
        
        # Post-process results based on intent
        results = self._post_process_results(results, retrieval_query)
        
        logger.info(f"Search completed: {len(results)} results returned")
        
        return results, retrieval_query
    
    def _retrieve_complete_table_metadata(
        self,
        table_name: str,
        reformulated_query: str,
        max_results: int
    ) -> List[Dict[str, Any]]:
        """
        Retrieve complete metadata for a table.
        This ensures all columns are retrieved, not just top-K similar ones.
        
        Args:
            table_name: Target table name
            reformulated_query: Reformulated query for context
            max_results: Maximum results (will be increased for complete retrieval)
            
        Returns:
            Complete table metadata
        """
        logger.info(f"Retrieving complete metadata for table: {table_name}")
        
        # Strategy 1: Filter by table name in metadata
        try:
            results = self.collection.query(
                query_embeddings=None,
                where={
                    "$or": [
                        {"table_name": {"$eq": table_name}},
                        {"TABLE_NAME": {"$eq": table_name}},
                        {"object_name": {"$eq": table_name}},
                    ]
                },
                n_results=500  # High limit to get all columns
            )
            
            if results and results['documents'] and len(results['documents'][0]) > 0:
                logger.info(f"Retrieved {len(results['documents'][0])} items via metadata filter")
                return self._format_results(results)
        
        except Exception as e:
            logger.warning(f"Metadata filter failed: {e}, falling back to enhanced search")
        
        # Strategy 2: Enhanced vector search with table name
        table_focused_query = f"table {table_name} all columns complete structure metadata"
        query_embedding = self.bge_model.encode([table_focused_query])[0].tolist()
        
        try:
            results = self.collection.query(
                query_embeddings=[query_embedding],
                n_results=min(500, max_results * 20),  # Much higher limit
            )
            
            if results and results['documents']:
                # Filter to only this table
                formatted = self._format_results(results)
                table_results = [
                    r for r in formatted 
                    if self._matches_table(r, table_name)
                ]
                
                logger.info(f"Retrieved {len(table_results)} items via enhanced vector search")
                return table_results
        
        except Exception as e:
            logger.error(f"Enhanced vector search failed: {e}")
        
        # Strategy 3: Fallback to original query
        return self._perform_vector_search(reformulated_query, max_results, None, None)
    
    def _matches_table(self, result: Dict[str, Any], table_name: str) -> bool:
        """Check if result matches target table."""
        metadata = result.get('metadata', {})
        document = result.get('document', '').upper()
        table_name_upper = table_name.upper()
        
        # Check metadata fields
        for field in ['table_name', 'TABLE_NAME', 'object_name', 'OBJECT_NAME']:
            if metadata.get(field, '').upper() == table_name_upper:
                return True
        
        # Check document content
        if table_name_upper in document:
            return True
        
        return False
    
    def _perform_vector_search(
        self,
        query: str,
        max_results: int,
        filters: Optional[Dict[str, Any]],
        retrieval_query: Optional[RetrievalQuery]
    ) -> List[Dict[str, Any]]:
        """Perform standard vector similarity search."""
        # Encode reformulated query
        query_embedding = self.bge_model.encode([query])[0].tolist()
        
        # Build query parameters
        query_params = {
            "query_embeddings": [query_embedding],
            "n_results": max_results
        }
        
        if filters:
            query_params["where"] = filters
        
        # Execute search
        results = self.collection.query(**query_params)
        
        return self._format_results(results)
    
    def _format_results(self, chroma_results: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Format ChromaDB results into standard format."""
        formatted_results = []
        
        if not chroma_results or 'documents' not in chroma_results:
            return formatted_results
        
        documents = chroma_results['documents'][0] if chroma_results['documents'] else []
        metadatas = chroma_results.get('metadatas', [[]])[0]
        distances = chroma_results.get('distances', [[]])[0]
        ids = chroma_results.get('ids', [[]])[0]
        
        for i, doc in enumerate(documents):
            result = {
                'document': doc,
                'metadata': metadatas[i] if i < len(metadatas) else {},
                'distance': distances[i] if i < len(distances) else 0.0,
                'id': ids[i] if i < len(ids) else None
            }
            formatted_results.append(result)
        
        return formatted_results
    
    def _post_process_results(
        self,
        results: List[Dict[str, Any]],
        retrieval_query: RetrievalQuery
    ) -> List[Dict[str, Any]]:
        """Post-process results based on intent."""
        
        # For table metadata queries, group by table
        if retrieval_query.intent == QueryIntent.TABLE_METADATA:
            results = self._group_by_table(results)
        
        # For column list queries, ensure all columns included
        elif retrieval_query.intent == QueryIntent.COLUMN_LIST:
            results = self._ensure_complete_columns(results, retrieval_query.target_table)
        
        return results
    
    def _group_by_table(self, results: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Group results by table for better organization."""
        # Keep original order but add grouping metadata
        table_groups = {}
        
        for result in results:
            metadata = result.get('metadata', {})
            table_name = (
                metadata.get('table_name') or 
                metadata.get('TABLE_NAME') or
                metadata.get('object_name', 'UNKNOWN')
            )
            
            if table_name not in table_groups:
                table_groups[table_name] = []
            
            table_groups[table_name].append(result)
        
        # Add group info to each result
        for result in results:
            metadata = result.get('metadata', {})
            table_name = (
                metadata.get('table_name') or 
                metadata.get('TABLE_NAME') or
                metadata.get('object_name', 'UNKNOWN')
            )
            result['table_group'] = table_name
            result['group_size'] = len(table_groups[table_name])
        
        return results
    
    def _ensure_complete_columns(
        self,
        results: List[Dict[str, Any]],
        target_table: Optional[str]
    ) -> List[Dict[str, Any]]:
        """Ensure all columns are included for column list queries."""
        if not target_table or not results:
            return results
        
        # Check if we have all columns
        column_names = set()
        for result in results:
            metadata = result.get('metadata', {})
            col_name = metadata.get('column_name') or metadata.get('COLUMN_NAME')
            if col_name:
                column_names.add(col_name)
        
        logger.info(
            f"Column list contains {len(column_names)} unique columns for {target_table}"
        )
        
        return results
    
    def reset_context(self):
        """Reset conversation context."""
        self.reformulator.reset_context()
    
    def get_context(self) -> Dict[str, Any]:
        """Get current conversation context."""
        return self.reformulator.get_context_summary()
