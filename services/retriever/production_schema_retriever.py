#!/usr/bin/env python3
"""
Production Schema Retriever for AML Database
Uses BGE-large-en-v1.5 embeddings and Neo4j graph for production-grade schema search.
"""

import logging
import os
from typing import Dict, List, Any, Optional, Tuple
import json
import re
from datetime import datetime

# Production components
try:
    from sentence_transformers import SentenceTransformer
    EMBEDDING_AVAILABLE = True
except ImportError:
    EMBEDDING_AVAILABLE = False

try:
    import chromadb
    VECTOR_DB_AVAILABLE = True
except ImportError:
    VECTOR_DB_AVAILABLE = False

from ..db import CatalogStore
from ..db.graph_store import ProductionGraphStore

logger = logging.getLogger(__name__)

class ProductionSchemaRetriever:
    """Production-grade schema retriever with state-of-the-art components."""
    
    def __init__(self, config: Dict[str, Any]):
        """Initialize with production configuration."""
        self.config = config
        self.catalog_store = CatalogStore(config)
        
        # Initialize production embedding model
        if EMBEDDING_AVAILABLE:
            self.embedding_model = SentenceTransformer("BAAI/bge-large-en-v1.5")
            logger.info("✅ Loaded BGE-large-en-v1.5 embedding model")
        else:
            logger.warning("⚠️ BGE embeddings not available, using fallback")
            self.embedding_model = None
        
        # Initialize vector database
        if VECTOR_DB_AVAILABLE:
            self.vector_client = chromadb.PersistentClient(path="warehouse/vectors")
            logger.info("✅ Connected to ChromaDB vector store")
        else:
            logger.warning("⚠️ ChromaDB not available, using fallback")
            self.vector_client = None
        
        # Initialize graph database
        graph_config = config.get('graph', {})
        if graph_config:
            self.graph_store = ProductionGraphStore(
                uri=graph_config.get('uri', 'neo4j://localhost:7687'),
                user=graph_config.get('user', 'neo4j'),
                password=graph_config.get('password', 'password'),
                database=graph_config.get('database', 'aml')
            )
            logger.info("✅ Connected to Neo4j graph database")
        else:
            logger.warning("⚠️ Graph database not configured, using fallback")
            self.graph_store = None
    
    def semantic_search(self, query: str, entity_types: List[str] = None, 
                       top_k: int = 20) -> List[Dict[str, Any]]:
        """Production semantic search using BGE embeddings and ChromaDB."""
        if not self.embedding_model or not self.vector_client:
            return self._fallback_search(query, entity_types, top_k)
        
        try:
            # Generate query embedding with BGE
            query_embedding = self.embedding_model.encode(
                f"query: {query}",  # BGE query prefix
                normalize_embeddings=True
            ).tolist()
            
            results = []
            
            # Search in relevant collections
            collections = entity_types if entity_types else ["tables", "columns", "views"]
            
            for collection_name in collections:
                try:
                    collection = self.vector_client.get_collection(f"aml_{collection_name}")
                    
                    # Vector similarity search
                    search_results = collection.query(
                        query_embeddings=[query_embedding],
                        n_results=top_k,
                        include=['metadatas', 'documents', 'distances']
                    )
                    
                    # Format results
                    for i, (doc, metadata, distance) in enumerate(zip(
                        search_results['documents'][0],
                        search_results['metadatas'][0],
                        search_results['distances'][0]
                    )):
                        results.append({
                            'entity_key': search_results['ids'][0][i],
                            'entity_type': metadata.get('entity_type'),
                            'name': metadata.get('name'),
                            'owner': metadata.get('owner'),
                            'description': metadata.get('description'),
                            'document': doc,
                            'similarity_score': 1 - distance,
                            'search_method': 'semantic_bge'
                        })
                
                except Exception as e:
                    logger.warning(f"Vector search failed for {collection_name}: {e}")
            
            # Sort by similarity score
            results.sort(key=lambda x: x['similarity_score'], reverse=True)
            return results[:top_k]
            
        except Exception as e:
            logger.error(f"Semantic search failed: {e}")
            return self._fallback_search(query, entity_types, top_k)
    
    def graph_search(self, query: str, max_depth: int = 2) -> List[Dict[str, Any]]:
        """Search using Neo4j graph relationships."""
        if not self.graph_store:
            return []
        
        try:
            with self.graph_store:
                # Use Neo4j full-text search
                entities = self.graph_store.search_entities(query, limit=10)
                
                enhanced_results = []
                
                for entity in entities:
                    entity_key = entity.get('key')
                    if entity_key:
                        # Get related entities
                        related = self.graph_store.find_related_entities(
                            entity_key, 
                            max_depth=max_depth
                        )
                        
                        # Get neighborhood for context
                        neighborhood = self.graph_store.get_entity_neighborhood(
                            entity_key, 
                            radius=1
                        )
                        
                        enhanced_results.append({
                            'entity': entity,
                            'related_entities': related,
                            'neighborhood': neighborhood,
                            'search_method': 'graph_neo4j'
                        })
                
                return enhanced_results
                
        except Exception as e:
            logger.error(f"Graph search failed: {e}")
            return []
    
    def hybrid_search(self, query: str, entity_types: List[str] = None,
                     semantic_weight: float = 0.7, graph_weight: float = 0.3,
                     top_k: int = 20) -> List[Dict[str, Any]]:
        """Hybrid search combining semantic and graph results."""
        
        # Get semantic results
        semantic_results = self.semantic_search(query, entity_types, top_k)
        
        # Get graph results
        graph_results = self.graph_search(query, max_depth=2)
        
        # Combine and rerank results
        combined_results = []
        
        # Add semantic results with weights
        for result in semantic_results:
            result['final_score'] = result['similarity_score'] * semantic_weight
            result['search_components'] = ['semantic']
            combined_results.append(result)
        
        # Enhance with graph information
        for graph_result in graph_results:
            entity = graph_result['entity']
            entity_key = entity.get('key')
            
            # Check if already in semantic results
            existing = next((r for r in combined_results if r.get('entity_key') == entity_key), None)
            
            if existing:
                # Enhance existing result
                existing['final_score'] += graph_weight * entity.get('search_score', 0.5)
                existing['search_components'].append('graph')
                existing['related_entities'] = graph_result['related_entities']
                existing['neighborhood'] = graph_result['neighborhood']
            else:
                # Add new graph result
                combined_results.append({
                    'entity_key': entity_key,
                    'entity_type': entity.get('entity_type'),
                    'name': entity.get('name'),
                    'owner': entity.get('owner'),
                    'description': entity.get('description', ''),
                    'final_score': graph_weight * entity.get('search_score', 0.5),
                    'search_components': ['graph'],
                    'related_entities': graph_result['related_entities'],
                    'neighborhood': graph_result['neighborhood'],
                    'search_method': 'graph_neo4j'
                })
        
        # Sort by final score
        combined_results.sort(key=lambda x: x['final_score'], reverse=True)
        
        return combined_results[:top_k]
    
    def find_join_paths(self, table1: str, table2: str, max_depth: int = 3) -> List[Dict[str, Any]]:
        """Find join paths between tables using graph analysis."""
        if not self.graph_store:
            return self._fallback_join_paths(table1, table2)
        
        try:
            with self.graph_store:
                # Create table keys
                table1_key = f"table:{table1}"
                table2_key = f"table:{table2}"
                
                # Find shortest paths
                paths = self.graph_store.find_path(table1_key, table2_key, max_depth)
                
                enhanced_paths = []
                
                for path in paths:
                    # Get detailed information for each node in path
                    path_details = []
                    
                    for node_key in path['node_keys']:
                        entity = self.graph_store.find_entity(node_key)
                        if entity:
                            path_details.append({
                                'entity_key': node_key,
                                'entity_type': entity.get('entity_type'),
                                'name': entity.get('name'),
                                'owner': entity.get('owner')
                            })
                    
                    enhanced_paths.append({
                        'path_length': path['path_length'],
                        'relationship_types': path['relationship_types'],
                        'path_details': path_details,
                        'join_confidence': self._calculate_join_confidence(path)
                    })
                
                # Sort by path length and confidence
                enhanced_paths.sort(key=lambda x: (x['path_length'], -x['join_confidence']))
                
                return enhanced_paths
                
        except Exception as e:
            logger.error(f"Graph join path analysis failed: {e}")
            return self._fallback_join_paths(table1, table2)
    
    def _calculate_join_confidence(self, path: Dict[str, Any]) -> float:
        """Calculate confidence score for join path."""
        base_score = 1.0 / (path['path_length'] + 1)
        
        # Boost score for foreign key relationships
        fk_boost = sum(1 for rel_type in path['relationship_types'] 
                      if 'FOREIGN_KEY' in rel_type or 'REFERENCES' in rel_type)
        
        return min(base_score + (fk_boost * 0.3), 1.0)
    
    def generate_sql_suggestions(self, query: str, top_k: int = 5) -> List[Dict[str, Any]]:
        """Generate SQL query suggestions based on natural language."""
        
        # Get relevant entities
        entities = self.hybrid_search(query, top_k=10)
        
        suggestions = []
        
        if entities:
            # Extract tables and columns
            tables = [e for e in entities if e.get('entity_type') == 'table'][:3]
            columns = [e for e in entities if e.get('entity_type') == 'column'][:5]
            
            for i, table in enumerate(tables):
                owner = table.get('owner', '')
                table_name = table.get('name', '')
                
                # Basic SELECT suggestion
                sql = f"SELECT * FROM {owner}.{table_name}"
                
                # Add WHERE clause if relevant columns found
                relevant_columns = [c for c in columns if c.get('owner') == owner]
                if relevant_columns:
                    col_name = relevant_columns[0].get('name', '')
                    sql += f" WHERE {col_name} = ?"
                
                sql += " LIMIT 100;"
                
                suggestions.append({
                    'sql': sql,
                    'confidence': table.get('final_score', 0.5),
                    'explanation': f"Query {table_name} table based on search relevance",
                    'entities_used': [table] + relevant_columns[:2]
                })
        
        return suggestions[:top_k]
    
    def _fallback_search(self, query: str, entity_types: List[str] = None, 
                        top_k: int = 20) -> List[Dict[str, Any]]:
        """Fallback search using catalog store."""
        try:
            return self.catalog_store.search_entities_bm25(
                query=query,
                entity_types=entity_types,
                limit=top_k
            )
        except Exception as e:
            logger.error(f"Fallback search failed: {e}")
            return []
    
    def _fallback_join_paths(self, table1: str, table2: str) -> List[Dict[str, Any]]:
        """Fallback join path analysis using catalog."""
        try:
            # Simple foreign key lookup
            relationships = self.catalog_store.get_table_relationships(table1)
            
            paths = []
            for rel in relationships:
                if rel.get('target_table') == table2:
                    paths.append({
                        'path_length': 1,
                        'relationship_types': [rel.get('relationship_type', 'UNKNOWN')],
                        'path_details': [
                            {'name': table1, 'entity_type': 'table'},
                            {'name': table2, 'entity_type': 'table'}
                        ],
                        'join_confidence': 0.8
                    })
            
            return paths
            
        except Exception as e:
            logger.error(f"Fallback join path analysis failed: {e}")
            return []