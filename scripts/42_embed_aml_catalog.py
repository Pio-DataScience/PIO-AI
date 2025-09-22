#!/usr/bin/env python3
"""
Script 42: Embed AML Catalog (Production)
Generate production-grade embeddings using BGE-large-en-v1.5 for AML catalog entities.
"""

import os
import sys
import argparse
import yaml
import logging
import json
from datetime import datetime
from typing import Dict, Any, List, Optional
import numpy as np
from tqdm import tqdm

# Add project root to path
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)

from services.db import CatalogStore

# Production embedding model
try:
    from sentence_transformers import SentenceTransformer
    EMBEDDING_AVAILABLE = True
except ImportError:
    EMBEDDING_AVAILABLE = False
    print("Installing sentence-transformers for BGE embeddings...")
    os.system("pip install sentence-transformers torch")
    try:
        from sentence_transformers import SentenceTransformer
        EMBEDDING_AVAILABLE = True
    except ImportError:
        EMBEDDING_AVAILABLE = False

# Vector database for production
try:
    import chromadb
    from chromadb.config import Settings
    VECTOR_DB_AVAILABLE = True
except ImportError:
    VECTOR_DB_AVAILABLE = False
    print("Installing ChromaDB for vector storage...")
    os.system("pip install chromadb")
    try:
        import chromadb
        from chromadb.config import Settings
        VECTOR_DB_AVAILABLE = True
    except ImportError:
        VECTOR_DB_AVAILABLE = False

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class ProductionEmbeddingGenerator:
    """Production-grade embedding generator using BGE-large-en-v1.5."""
    
    def __init__(self, model_name: str = "BAAI/bge-large-en-v1.5"):
        """Initialize with production embedding model."""
        if not EMBEDDING_AVAILABLE:
            raise RuntimeError("sentence-transformers not available. Install with: pip install sentence-transformers torch")
        
        self.model_name = model_name
        self.model = None
        self.embedding_dim = 1024  # BGE-large-en-v1.5 dimension
        logger.info(f"Initializing production embedding model: {model_name}")
    
    def load_model(self):
        """Load the BGE model."""
        if self.model is None:
            logger.info(f"Loading {self.model_name} - this may take a few minutes...")
            self.model = SentenceTransformer(self.model_name)
            logger.info("Model loaded successfully")
    
    def generate_embedding(self, text: str) -> List[float]:
        """Generate embedding for text using BGE-large-en-v1.5."""
        if self.model is None:
            self.load_model()
        
        # BGE models work best with query prefixes for retrieval
        embedding = self.model.encode(text, normalize_embeddings=True)
        return embedding.tolist()
    
    def generate_batch_embeddings(self, texts: List[str], batch_size: int = 32) -> List[List[float]]:
        """Generate embeddings for multiple texts efficiently with memory management."""
        if self.model is None:
            self.load_model()
        
        embeddings = []
        # Use smaller internal batches for large models
        internal_batch_size = min(batch_size, 4)
        
        for i in tqdm(range(0, len(texts), internal_batch_size), desc="Generating embeddings"):
            batch = texts[i:i + internal_batch_size]
            try:
                batch_embeddings = self.model.encode(
                    batch, 
                    normalize_embeddings=True, 
                    batch_size=internal_batch_size,
                    show_progress_bar=False  # Disable internal progress bar
                )
                embeddings.extend([emb.tolist() for emb in batch_embeddings])
            except Exception as e:
                logger.error(f"Error processing batch {i//internal_batch_size}: {e}")
                # Add placeholder embeddings to maintain alignment
                for _ in batch:
                    embeddings.append([0.0] * self.embedding_dim)
        
        return embeddings
class ProductionVectorStore:
    """Production vector store using ChromaDB."""
    
    def __init__(self, persist_directory: str = "warehouse/vectors"):
        """Initialize ChromaDB for production vector storage."""
        if not VECTOR_DB_AVAILABLE:
            raise RuntimeError("ChromaDB not available. Install with: pip install chromadb")
        
        self.persist_directory = persist_directory
        os.makedirs(persist_directory, exist_ok=True)
        
        # Initialize ChromaDB with persistence
        self.client = chromadb.PersistentClient(
            path=persist_directory,
            settings=Settings(
                anonymized_telemetry=False,
                allow_reset=True
            )
        )
        
        # Create collections for different entity types
        self.collections = {}
        self._initialize_collections()
    
    def _initialize_collections(self):
        """Initialize collections for different entity types."""
        # Map singular entity types to plural collection names
        entity_mappings = {
            "table": "tables",
            "column": "columns", 
            "view": "views",
            "schema": "schemas",
            "relationship": "relationships"
        }
        
        for singular, plural in entity_mappings.items():
            try:
                collection = self.client.get_collection(f"aml_{plural}")
                logger.info(f"Using existing collection: aml_{plural}")
            except:
                collection = self.client.create_collection(
                    name=f"aml_{plural}",
                    metadata={"description": f"AML {plural} embeddings"}
                )
                logger.info(f"Created new collection: aml_{plural}")
            
            # Map both singular and plural to the same collection
            self.collections[singular] = collection
            self.collections[plural] = collection
    
    def add_embeddings(self, entity_type: str, entities: List[Dict[str, Any]], embeddings: List[List[float]]):
        """Add embeddings to the vector store."""
        if entity_type not in self.collections:
            raise ValueError(f"Unknown entity type: {entity_type}")
        
        collection = self.collections[entity_type]
        
        # Generate unique IDs and prepare data for ChromaDB
        ids = []
        documents = []
        metadatas = []
        
        for i, entity in enumerate(entities):
            # Generate unique ID based on entity type and key fields
            if entity_type == 'table':
                entity_id = f"table_{entity.get('owner', '')}_{entity.get('table_name', '')}"
            elif entity_type == 'column':
                entity_id = f"column_{entity.get('owner', '')}_{entity.get('table_name', '')}_{entity.get('column_name', '')}"
            elif entity_type == 'view':
                entity_id = f"view_{entity.get('owner', '')}_{entity.get('view_name', '')}"
            elif entity_type == 'constraint':
                entity_id = f"constraint_{entity.get('owner', '')}_{entity.get('constraint_name', '')}"
            elif entity_type == 'index':
                entity_id = f"index_{entity.get('owner', '')}_{entity.get('index_name', '')}"
            else:
                entity_id = f"{entity_type}_{i}"
            
            ids.append(entity_id)
            documents.append(entity.get('embedding_text', ''))
            
            # Build metadata with only non-null values
            metadata = {}
            for key, value in {
                'entity_type': entity.get('entity_type', entity_type),
                'owner': entity.get('owner', ''),
                'table_name': entity.get('table_name', ''),
                'name': entity.get('table_name') or entity.get('column_name') or entity.get('view_name') or entity.get('constraint_name') or entity.get('index_name') or '',
                'data_type': entity.get('data_type', ''),
                'comments': entity.get('comments', '')
            }.items():
                if value is not None and value != '':
                    metadata[key] = str(value)  # Ensure all values are strings
            
            metadatas.append(metadata)
        
        # Add to collection
        collection.add(
            ids=ids,
            embeddings=embeddings,
            documents=documents,
            metadatas=metadatas
        )
        
        logger.info(f"Added {len(entities)} {entity_type} embeddings to vector store")
        
        logger.info(f"Added {len(entities)} {entity_type} embeddings to vector store")
    
    def search_similar(self, entity_type: str, query_embedding: List[float], top_k: int = 10) -> List[Dict[str, Any]]:
        """Search for similar entities using vector similarity."""
        if entity_type not in self.collections:
            return []
        
        collection = self.collections[entity_type]
        results = collection.query(
            query_embeddings=[query_embedding],
            n_results=top_k,
            include=['metadatas', 'documents', 'distances']
        )
        
        # Format results
        formatted_results = []
        for i, (doc, metadata, distance) in enumerate(zip(
            results['documents'][0],
            results['metadatas'][0], 
            results['distances'][0]
        )):
            formatted_results.append({
                'entity_key': results['ids'][0][i],
                'document': doc,
                'metadata': metadata,
                'similarity_score': 1 - distance,  # Convert distance to similarity
                'rank': i + 1
            })
        
        return formatted_results
    
    def get_collection_stats(self) -> Dict[str, int]:
        """Get statistics for all collections."""
        stats = {}
        for entity_type, collection in self.collections.items():
            stats[entity_type] = collection.count()
        return stats

def load_config() -> Dict[str, Any]:
    """Load database configuration."""
    config_path = os.path.join(project_root, 'config', 'database.yaml')
    
    with open(config_path, 'r') as f:
        config = yaml.safe_load(f)
    
    return config

def create_embedding_text(entity: Dict[str, Any]) -> str:
    """Create rich text representation for embedding generation."""
    entity_type = entity.get('entity_type', '')
    
    if entity_type == 'table':
        return (
            f"Table: {entity.get('table_name', '')} "
            f"Owner: {entity.get('owner', '')} "
            f"Comments: {entity.get('comments', '')} "
            f"Tablespace: {entity.get('tablespace_name', '')} "
            f"Status: {entity.get('status', '')}"
        )
    elif entity_type == 'column':
        return (
            f"Column: {entity.get('column_name', '')} "
            f"Table: {entity.get('table_name', '')} "
            f"Owner: {entity.get('owner', '')} "
            f"Data Type: {entity.get('data_type', '')} "
            f"Nullable: {entity.get('nullable', '')} "
            f"Comments: {entity.get('comments', '')}"
        )
    elif entity_type == 'view':
        return (
            f"View: {entity.get('view_name', '')} "
            f"Owner: {entity.get('owner', '')} "
            f"Comments: {entity.get('comments', '')} "
            f"Type: {entity.get('view_type_owner', '')} "
            f"Text Length: {entity.get('text_length', '')}"
        )
    elif entity_type == 'constraint':
        return (
            f"Constraint: {entity.get('constraint_name', '')} "
            f"Table: {entity.get('table_name', '')} "
            f"Owner: {entity.get('owner', '')} "
            f"Type: {entity.get('constraint_type', '')} "
            f"Status: {entity.get('status', '')}"
        )
    elif entity_type == 'index':
        return (
            f"Index: {entity.get('index_name', '')} "
            f"Table: {entity.get('table_name', '')} "
            f"Owner: {entity.get('owner', '')} "
            f"Type: {entity.get('index_type', '')} "
            f"Uniqueness: {entity.get('uniqueness', '')}"
        )
    else:
        # Generic fallback
        text_parts = []
        for key, value in entity.items():
            if key not in ['entity_key', 'entity_type', 'created_at'] and value:
                text_parts.append(f"{key}: {value}")
        return " ".join(text_parts)

def embed_catalog_entities(config: Dict[str, Any], batch_size: int = 100, entity_types: Optional[List[str]] = None):
    """Generate and store embeddings for catalog entities."""
    # Initialize components
    catalog_path = config.get('catalog', {}).get('path', 'warehouse/db/aml_catalog.sqlite')
    catalog_store = CatalogStore(catalog_path)
    embedding_generator = ProductionEmbeddingGenerator()
    vector_store = ProductionVectorStore()
    
    # Default entity types to process
    if entity_types is None:
        entity_types = ['table', 'column', 'view', 'constraint', 'index']
    
    logger.info(f"Starting embedding generation for entity types: {entity_types}")
    
    # Get all entities from catalog
    all_entities = catalog_store.get_catalog_entities_for_search()
    logger.info(f"Found {len(all_entities)} total entities in catalog")
    
    total_embedded = 0
    
    for entity_type in entity_types:
        logger.info(f"Processing {entity_type} entities...")
        
        # Filter entities by type
        entities = [e for e in all_entities if e.get('entity_type') == entity_type]
        
        if not entities:
            logger.warning(f"No {entity_type} entities found")
            continue
        
        logger.info(f"Found {len(entities)} {entity_type} entities")
        
        # Process in batches
        for i in range(0, len(entities), batch_size):
            batch = entities[i:i + batch_size]
            
            # Create embedding texts
            for entity in batch:
                entity['embedding_text'] = create_embedding_text(entity)
            
            # Generate embeddings
            texts = [entity['embedding_text'] for entity in batch]
            embeddings = embedding_generator.generate_batch_embeddings(texts, batch_size=32)
            
            # Store in vector database  
            try:
                vector_store.add_embeddings(entity_type, batch, embeddings)
                total_embedded += len(batch)
                logger.info(f"Embedded batch {i//batch_size + 1}/{(len(entities) + batch_size - 1)//batch_size} "
                           f"for {entity_type} ({len(batch)} entities)")
            except Exception as e:
                logger.error(f"Failed to store embeddings for {entity_type}: {e}")
    
    # Print final statistics
    try:
        stats = vector_store.get_collection_stats()
        logger.info("Embedding generation completed!")
        logger.info("Collection Statistics:")
        for entity_type, count in stats.items():
            logger.info(f"  {entity_type}: {count} embeddings")
        logger.info(f"Total entities embedded: {total_embedded}")
    except Exception as e:
        logger.warning(f"Could not get collection stats: {e}")
        logger.info(f"Total entities embedded: {total_embedded}")
def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(description='Generate embeddings for AML catalog entities')
    parser.add_argument('--batch-size', type=int, default=100,
                       help='Batch size for processing entities (default: 100)')
    parser.add_argument('--entity-types', nargs='+', 
                       choices=['table', 'column', 'view', 'constraint', 'index'],
                       help='Entity types to process (default: all)')
    parser.add_argument('--reset', action='store_true',
                       help='Reset vector store before embedding')
    
    args = parser.parse_args()
    
    try:
        # Load configuration
        config = load_config()
        
        # Reset vector store if requested
        if args.reset:
            vector_store = ProductionVectorStore()
            logger.info("Vector store reset requested - clearing existing embeddings")
            # Note: ChromaDB doesn't have a direct reset, so we recreate collections
            for collection_name in vector_store.collections:
                try:
                    vector_store.client.delete_collection(f"aml_{collection_name}")
                except:
                    pass
            vector_store._initialize_collections()
        
        # Generate embeddings
        embed_catalog_entities(
            config=config,
            batch_size=args.batch_size,
            entity_types=args.entity_types
        )
        
        logger.info("✅ AML catalog embedding completed successfully!")
        
    except Exception as e:
        logger.error(f"❌ Error during embedding generation: {e}")
        raise

if __name__ == "__main__":
    main()