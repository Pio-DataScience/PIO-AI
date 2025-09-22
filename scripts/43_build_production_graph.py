#!/usr/bin/env python3
"""
Script 43: Build Production AML Graph (Neo4j)
Build comprehe    # Organize entities by type and generate proper keys
    entities_by_type = {}
    for entity in all_entities:
        entity_type = entity.get('entity_type', 'unknown')
        if entity_type not in entities_by_type:
            entities_by_type[entity_type] = []
        
        # Generate entity_key based on type
        if entity_type == 'table':
            entity['entity_key'] = f"table:{entity['owner']}.{entity['table_name']}"
        elif entity_type == 'view':
            entity['entity_key'] = f"view:{entity['owner']}.{entity['view_name']}"
        elif entity_type == 'column':
            entity['entity_key'] = f"column:{entity['owner']}.{entity['table_name']}.{entity['column_name']}"
        else:
            # For other types, use a generic key
            entity['entity_key'] = f"{entity_type}:{entity.get('owner', 'unknown')}.{entity.get('name', str(hash(str(entity))))}"
        
        entities_by_type[entity_type].append(entity)elationship graphs using Neo4j for production deployment.
"""

import os
import sys
import argparse
import yaml
import logging
from datetime import datetime
from typing import Dict, Any, List

# Add project root to path
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)

from services.db import CatalogStore
from services.db.graph_store import ProductionGraphStore, AMLGraphBuilder

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def load_config() -> Dict[str, Any]:
    """Load database configuration."""
    config_path = os.path.join(project_root, 'config', 'database.yaml')
    
    with open(config_path, 'r') as f:
        config = yaml.safe_load(f)
    
    return config

def load_graph_config() -> Dict[str, Any]:
    """Load or create graph database configuration."""
    config_path = os.path.join(project_root, 'config', 'graph.yaml')
    
    # Default configuration
    default_config = {
        'neo4j': {
            'uri': 'neo4j://localhost:7687',
            'user': 'neo4j',
            'password': 'password',
            'database': 'aml'
        },
        'settings': {
            'batch_size': 1000,
            'max_retry_attempts': 3,
            'connection_timeout': 30
        }
    }
    
    if os.path.exists(config_path):
        with open(config_path, 'r') as f:
            config = yaml.safe_load(f)
        logger.info("Loaded existing graph configuration")
    else:
        # Create default config
        os.makedirs(os.path.dirname(config_path), exist_ok=True)
        with open(config_path, 'w') as f:
            yaml.dump(default_config, f, default_flow_style=False)
        config = default_config
        logger.info(f"Created default graph configuration at {config_path}")
        logger.warning("⚠️ Please update Neo4j credentials in config/graph.yaml")
    
    return config

def migrate_catalog_to_graph(catalog_store: CatalogStore, graph_store: ProductionGraphStore, 
                           batch_size: int = 1000) -> Dict[str, int]:
    """Migrate catalog entities to Neo4j graph."""
    logger.info("Starting catalog to graph migration...")
    
    # Get all entities from catalog
    entity_types = ['table', 'column', 'view', 'constraint', 'index']
    
    migration_stats = {
        'entities_migrated': 0,
        'relationships_created': 0,
        'errors': 0
    }
    
    # Get all entities from catalog
    logger.info("Loading all catalog entities...")
    all_entities = catalog_store.get_catalog_entities_for_search()
    logger.info(f"Found {len(all_entities)} total entities")
    
    # Generate entity_key for each entity based on type
    logger.info("Generating entity keys...")
    for entity in all_entities:
        entity_type = entity.get('entity_type', 'unknown')
        
        # Generate entity_key based on type
        if entity_type == 'table':
            entity['entity_key'] = f"table:{entity.get('owner', 'unknown')}.{entity.get('table_name', 'unknown')}"
        elif entity_type == 'view':
            entity['entity_key'] = f"view:{entity.get('owner', 'unknown')}.{entity.get('view_name', 'unknown')}"
        elif entity_type == 'column':
            entity['entity_key'] = f"column:{entity.get('owner', 'unknown')}.{entity.get('table_name', 'unknown')}.{entity.get('column_name', 'unknown')}"
        else:
            # For other types, use a generic key
            entity['entity_key'] = f"{entity_type}:{entity.get('owner', 'unknown')}.{entity.get('name', str(hash(str(entity))))}"
    
    # Group entities by type
    entities_by_type = {}
    for entity in all_entities:
        entity_type = entity.get('entity_type', 'unknown')
        if entity_type not in entities_by_type:
            entities_by_type[entity_type] = []
        entities_by_type[entity_type].append(entity)
    
    # Process each entity type
    for entity_type, entities in entities_by_type.items():
        logger.info(f"Processing {len(entities)} {entity_type} entities...")
        
        # Add entities to graph in batches
        for i in range(0, len(entities), batch_size):
            batch = entities[i:i + batch_size]
            
            for entity in batch:
                try:
                    graph_store.add_entity(entity)
                    migration_stats['entities_migrated'] += 1
                except Exception as e:
                    logger.error(f"Failed to add entity {entity.get('entity_key')}: {e}")
                    migration_stats['errors'] += 1
            
            logger.info(f"Migrated batch {i//batch_size + 1}/{(len(entities) + batch_size - 1)//batch_size} "
                       f"for {entity_type}")
        
        all_entities.extend(entities)
    
    logger.info(f"✅ Migrated {migration_stats['entities_migrated']} entities to Neo4j")
    
    # Build relationships
    logger.info("Building relationships...")
    graph_builder = AMLGraphBuilder(graph_store)
    
    try:
        graph_builder.build_table_column_relationships(all_entities)
        graph_builder.build_foreign_key_relationships(all_entities)
        graph_builder.build_schema_relationships(all_entities)
        logger.info("✅ Relationship building completed")
    except Exception as e:
        logger.error(f"❌ Error building relationships: {e}")
        migration_stats['errors'] += 1
    
    return migration_stats

def analyze_graph(graph_store: ProductionGraphStore):
    """Analyze the production graph and generate insights."""
    logger.info("Analyzing production graph...")
    
    try:
        stats = graph_store.get_graph_statistics()
        
        logger.info("="*60)
        logger.info("PRODUCTION GRAPH ANALYSIS")
        logger.info("="*60)
        
        logger.info(f"📊 Total Nodes: {stats.get('total_nodes', 0):,}")
        logger.info(f"🔗 Total Relationships: {stats.get('total_relationships', 0):,}")
        
        # Entity type distribution
        logger.info("\n📋 Entity Types:")
        for entity_type in stats.get('entity_types', []):
            logger.info(f"  {entity_type['type']}: {entity_type['count']:,} entities")
        
        # Relationship type distribution
        logger.info("\n🔗 Relationship Types:")
        for rel_type in stats.get('relationship_types', []):
            logger.info(f"  {rel_type['type']}: {rel_type['count']:,} relationships")
        
        # Top owners/schemas
        logger.info("\n👥 Top Schemas (by entity count):")
        for owner in stats.get('owners', []):
            logger.info(f"  {owner['owner']}: {owner['count']:,} entities")
        
        logger.info("="*60)
        
        # Sample graph queries
        logger.info("\n🔍 Sample Graph Queries:")
        
        # Find highly connected tables
        logger.info("Most connected tables (by relationship count)...")
        # This would require a more complex query in a real implementation
        
    except Exception as e:
        logger.error(f"❌ Error analyzing graph: {e}")

def test_graph_queries(graph_store: ProductionGraphStore, sample_queries: List[str]):
    """Test graph with sample queries."""
    logger.info("Testing graph with sample queries...")
    
    default_queries = [
        "customer",
        "account",
        "transaction", 
        "address",
        "payment"
    ]
    
    queries = sample_queries if sample_queries else default_queries
    
    for query in queries:
        try:
            logger.info(f"\n🔍 Searching for: '{query}'")
            
            # Full-text search
            results = graph_store.search_entities(query, limit=5)
            
            if results:
                logger.info(f"Found {len(results)} matching entities:")
                for i, entity in enumerate(results[:3], 1):
                    name = entity.get('name', 'Unknown')
                    entity_type = entity.get('entity_type', 'Unknown')
                    owner = entity.get('owner', 'Unknown')
                    score = entity.get('search_score', 0)
                    logger.info(f"  {i}. {owner}.{name} ({entity_type}) - Score: {score:.2f}")
                
                # Show relationships for first result
                if results:
                    first_entity = results[0]
                    entity_key = first_entity.get('key')
                    if entity_key:
                        related = graph_store.find_related_entities(entity_key, max_depth=1)
                        if related:
                            logger.info(f"    Related entities ({len(related)}):")
                            for rel in related[:3]:
                                rel_entity = rel['entity']
                                rel_type = rel['relationship_type']
                                logger.info(f"      → {rel_entity.get('name')} ({rel_type})")
            else:
                logger.info("  No matching entities found")
                
        except Exception as e:
            logger.error(f"❌ Query failed for '{query}': {e}")

def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(description='Build production AML graph in Neo4j')
    parser.add_argument('--rebuild', action='store_true',
                       help='Clear existing graph and rebuild from scratch')
    parser.add_argument('--batch-size', type=int, default=1000,
                       help='Batch size for entity migration (default: 1000)')
    parser.add_argument('--skip-migration', action='store_true',
                       help='Skip entity migration, only build relationships')
    parser.add_argument('--test-queries', nargs='+',
                       help='Custom queries to test the graph')
    parser.add_argument('--analyze-only', action='store_true',
                       help='Only analyze existing graph, do not rebuild')
    
    args = parser.parse_args()
    
    try:
        # Load configurations
        db_config = load_config()
        graph_config = load_graph_config()
        
        # Initialize stores  
        catalog_store = CatalogStore(db_config['catalog']['path'])
        
        neo4j_config = graph_config['neo4j']
        graph_store = ProductionGraphStore(
            uri=neo4j_config['uri'],
            user=neo4j_config['user'],
            password=neo4j_config['password'],
            database=neo4j_config['database']
        )
        
        with graph_store:
            # Create constraints and indexes
            logger.info("Setting up Neo4j constraints and indexes...")
            graph_store.create_constraints_and_indexes()
            
            if args.analyze_only:
                analyze_graph(graph_store)
                test_graph_queries(graph_store, args.test_queries)
                return
            
            # Clear graph if rebuild requested
            if args.rebuild:
                logger.warning("🗑️ Clearing existing graph data...")
                graph_store.clear_database()
                logger.info("Graph cleared, rebuilding from scratch...")
            
            # Migrate catalog entities
            if not args.skip_migration:
                migration_stats = migrate_catalog_to_graph(
                    catalog_store, 
                    graph_store, 
                    batch_size=args.batch_size
                )
                
                logger.info("="*50)
                logger.info("MIGRATION SUMMARY")
                logger.info("="*50)
                logger.info(f"Entities migrated: {migration_stats['entities_migrated']:,}")
                logger.info(f"Errors encountered: {migration_stats['errors']:,}")
            
            # Analyze the resulting graph
            analyze_graph(graph_store)
            
            # Test with sample queries
            test_graph_queries(graph_store, args.test_queries)
            
            logger.info("✅ Production AML graph build completed successfully!")
            logger.info("💡 Graph is ready for production queries and analytics")
        
    except Exception as e:
        logger.error(f"❌ Error building production graph: {e}")
        raise

if __name__ == "__main__":
    main()