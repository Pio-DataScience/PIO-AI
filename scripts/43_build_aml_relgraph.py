#!/usr/bin/env python3
"""
Script 43: Build AML Relationship Graph
Build and persist relationship graphs from catalog constraints.
"""

import os
import sys
import argparse
import yaml
import logging
import json
from datetime import datetime
from typing import Dict, Any

# Add project root to path
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)

from services.db import CatalogStore, RelationshipBuilder

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

def analyze_graph_connectivity(builder: RelationshipBuilder) -> Dict[str, Any]:
    """Analyze graph connectivity and structure."""
    graph = builder.graph
    
    if graph.number_of_nodes() == 0:
        return {"error": "No nodes in graph"}
    
    # Basic graph stats
    stats = {
        "nodes": graph.number_of_nodes(),
        "edges": graph.number_of_edges(),
        "density": round(graph.number_of_edges() / (graph.number_of_nodes() * (graph.number_of_nodes() - 1)) * 2, 4) if graph.number_of_nodes() > 1 else 0
    }
    
    # Degree analysis
    in_degrees = [graph.in_degree(node) for node in graph.nodes()]
    out_degrees = [graph.out_degree(node) for node in graph.nodes()]
    
    stats.update({
        "avg_in_degree": round(sum(in_degrees) / len(in_degrees), 2),
        "avg_out_degree": round(sum(out_degrees) / len(out_degrees), 2),
        "max_in_degree": max(in_degrees) if in_degrees else 0,
        "max_out_degree": max(out_degrees) if out_degrees else 0
    })
    
    # Find most connected tables
    most_referenced = max(graph.nodes(), key=lambda n: graph.in_degree(n)) if graph.nodes() else None
    most_referencing = max(graph.nodes(), key=lambda n: graph.out_degree(n)) if graph.nodes() else None
    
    if most_referenced:
        stats["most_referenced_table"] = {
            "table": most_referenced,
            "incoming_references": graph.in_degree(most_referenced)
        }
    
    if most_referencing:
        stats["most_referencing_table"] = {
            "table": most_referencing,
            "outgoing_references": graph.out_degree(most_referencing)
        }
    
    # Connectivity analysis
    import networkx as nx
    
    try:
        # For directed graphs, check weak connectivity
        is_connected = nx.is_weakly_connected(graph)
        connected_components = list(nx.weakly_connected_components(graph))
        
        stats.update({
            "is_connected": is_connected,
            "connected_components": len(connected_components),
            "largest_component_size": max(len(comp) for comp in connected_components) if connected_components else 0
        })
        
        # If not connected, find isolated tables
        if not is_connected and len(connected_components) > 1:
            isolated_tables = [list(comp) for comp in connected_components if len(comp) == 1]
            stats["isolated_tables"] = len(isolated_tables)
            
            if isolated_tables:
                stats["isolated_table_examples"] = isolated_tables[:5]  # First 5 examples
    
    except Exception as e:
        logger.warning(f"Error analyzing connectivity: {e}")
    
    return stats

def test_join_paths(builder: RelationshipBuilder, test_cases: list = None) -> Dict[str, Any]:
    """Test join path finding between tables."""
    if test_cases is None:
        # Default test cases - these would be customized for your AML domain
        test_cases = [
            ("AML_CUSTOMER", "AML_ACCOUNT"),
            ("AML_TRANSACTION", "AML_CUSTOMER"),
            ("AML_ALERT", "AML_SCENARIO"),
            ("PIO_AML_WATCHLIST", "PIO_AML_CUSTOMER")
        ]
    
    results = {
        "test_cases": len(test_cases),
        "successful_paths": 0,
        "failed_paths": 0,
        "path_details": []
    }
    
    for table1, table2 in test_cases:
        logger.info(f"Testing join path: {table1} -> {table2}")
        
        try:
            join_path = builder.find_join_path(table1, table2)
            
            if join_path:
                results["successful_paths"] += 1
                path_detail = {
                    "source": table1,
                    "target": table2,
                    "found": True,
                    "path_length": join_path.path_length,
                    "quality": join_path.total_quality,
                    "path": join_path.path_nodes
                }
                logger.info(f"  ✓ Path found: {' -> '.join(join_path.path_nodes)} (quality: {join_path.total_quality})")
            else:
                results["failed_paths"] += 1
                path_detail = {
                    "source": table1,
                    "target": table2,
                    "found": False,
                    "reason": "No path found"
                }
                logger.info(f"  ✗ No path found")
            
            results["path_details"].append(path_detail)
            
        except Exception as e:
            results["failed_paths"] += 1
            path_detail = {
                "source": table1,
                "target": table2,
                "found": False,
                "reason": f"Error: {str(e)}"
            }
            results["path_details"].append(path_detail)
            logger.error(f"  ✗ Error finding path: {e}")
    
    return results

def export_graph_summary(builder: RelationshipBuilder, output_dir: str) -> str:
    """Export graph summary as JSON."""
    summary_file = os.path.join(output_dir, "graph_summary.json")
    
    # Get graph data
    graph_data = builder.export_graph_data()
    
    # Add analysis
    connectivity_stats = analyze_graph_connectivity(builder)
    
    summary = {
        "generated_at": datetime.utcnow().isoformat(),
        "graph_stats": connectivity_stats,
        "graph_data": graph_data
    }
    
    with open(summary_file, 'w') as f:
        json.dump(summary, f, indent=2)
    
    logger.info(f"Graph summary exported to: {summary_file}")
    return summary_file

def build_relationship_graph(config: Dict[str, Any], analyze_only: bool = False) -> Dict[str, Any]:
    """
    Build relationship graph from catalog constraints.
    
    Args:
        config: Database configuration
        analyze_only: If True, analyze existing relationships without rebuilding
        
    Returns:
        Build statistics
    """
    start_time = datetime.utcnow()
    
    # Setup catalog
    catalog_path = config['catalog']['path']
    if not os.path.isabs(catalog_path):
        catalog_path = os.path.join(project_root, catalog_path)
    
    catalog = CatalogStore(catalog_path)
    
    # Setup relationship builder
    builder = RelationshipBuilder(catalog)
    
    if not analyze_only:
        logger.info("Building relationship graph from catalog constraints...")
        build_stats = builder.build_relationships()
    else:
        logger.info("Analyzing existing relationships...")
        # Load existing relationships
        relationships = catalog.get_relationships()
        build_stats = {
            "total_relationships": len(relationships),
            "message": "Loaded existing relationships"
        }
        # Build the NetworkX graph from existing relationships
        builder._build_networkx_graph()
    
    # Analyze graph connectivity
    logger.info("Analyzing graph connectivity...")
    connectivity_stats = analyze_graph_connectivity(builder)
    
    # Test join paths
    logger.info("Testing join path finding...")
    join_test_results = test_join_paths(builder)
    
    # Export graph summary if directory configured
    graphs_config = config.get('graphs', {})
    if graphs_config.get('export_dir') and graphs_config.get('build_relationship_graph', True):
        export_dir = graphs_config['export_dir']
        if not os.path.isabs(export_dir):
            export_dir = os.path.join(project_root, export_dir)
        
        os.makedirs(export_dir, exist_ok=True)
        summary_file = export_graph_summary(builder, export_dir)
    
    end_time = datetime.utcnow()
    duration = (end_time - start_time).total_seconds()
    
    return {
        "build_stats": build_stats,
        "connectivity_stats": connectivity_stats,
        "join_test_results": join_test_results,
        "duration_seconds": duration,
        "start_time": start_time.isoformat(),
        "end_time": end_time.isoformat()
    }

def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Build AML relationship graph from catalog constraints",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Build relationship graph from scratch
  python scripts/43_build_aml_relgraph.py
  
  # Analyze existing relationships without rebuilding
  python scripts/43_build_aml_relgraph.py --analyze-only
  
  # Test specific join paths
  python scripts/43_build_aml_relgraph.py --test-paths "TABLE1,TABLE2" "TABLE3,TABLE4"
  
  # Verbose logging
  python scripts/43_build_aml_relgraph.py --verbose
        """
    )
    
    parser.add_argument(
        '--analyze-only',
        action='store_true',
        help='Analyze existing relationships without rebuilding graph'
    )
    parser.add_argument(
        '--test-paths',
        nargs='*',
        help='Test specific join paths (format: "TABLE1,TABLE2")'
    )
    parser.add_argument(
        '--verbose', '-v',
        action='store_true',
        help='Enable verbose logging'
    )
    
    args = parser.parse_args()
    
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)
        logging.getLogger('services.db').setLevel(logging.DEBUG)
    
    try:
        # Load configuration
        logger.info("Loading configuration...")
        config = load_config()
        
        # Test catalog
        catalog_path = config['catalog']['path']
        if not os.path.isabs(catalog_path):
            catalog_path = os.path.join(project_root, catalog_path)
        
        catalog = CatalogStore(catalog_path)
        health = catalog.health_check()
        
        if health['status'] != 'healthy':
            logger.error(f"Catalog is not healthy: {health}")
            sys.exit(1)
        
        logger.info(f"Catalog health: {health['catalog_tables']} tables, {health['relationships']} relationships")
        
        # Parse custom test paths if provided
        custom_test_cases = None
        if args.test_paths:
            custom_test_cases = []
            for path_spec in args.test_paths:
                if ',' in path_spec:
                    table1, table2 = path_spec.split(',', 1)
                    custom_test_cases.append((table1.strip(), table2.strip()))
                else:
                    logger.warning(f"Invalid path specification: {path_spec} (expected 'TABLE1,TABLE2')")
        
        # Build/analyze relationship graph
        logger.info("Processing relationship graph...")
        results = build_relationship_graph(config, args.analyze_only)
        
        # Display results
        logger.info("="*50)
        logger.info("RELATIONSHIP GRAPH SUMMARY")
        logger.info("="*50)
        
        build_stats = results['build_stats']
        connectivity_stats = results['connectivity_stats']
        join_tests = results['join_test_results']
        
        logger.info(f"Build duration: {results['duration_seconds']:.2f} seconds")
        logger.info(f"Total relationships: {build_stats.get('total_relationships', 0)}")
        
        if 'error' not in connectivity_stats:
            logger.info(f"Graph nodes: {connectivity_stats['nodes']}")
            logger.info(f"Graph edges: {connectivity_stats['edges']}")
            logger.info(f"Graph density: {connectivity_stats['density']}")
            logger.info(f"Connected components: {connectivity_stats.get('connected_components', 'Unknown')}")
            
            if 'most_referenced_table' in connectivity_stats:
                most_ref = connectivity_stats['most_referenced_table']
                logger.info(f"Most referenced table: {most_ref['table']} ({most_ref['incoming_references']} refs)")
            
            if 'most_referencing_table' in connectivity_stats:
                most_referencing = connectivity_stats['most_referencing_table']
                logger.info(f"Most referencing table: {most_referencing['table']} ({most_referencing['outgoing_references']} refs)")
        
        logger.info(f"Join path tests: {join_tests['successful_paths']}/{join_tests['test_cases']} successful")
        
        # Show successful paths
        for path_detail in join_tests['path_details']:
            if path_detail['found']:
                logger.info(f"  ✓ {path_detail['source']} -> {path_detail['target']}: {' -> '.join(path_detail['path'])} (quality: {path_detail['quality']})")
        
        # Test custom paths if provided
        if custom_test_cases:
            logger.info("\nCustom path tests:")
            builder = RelationshipBuilder(catalog)
            builder.build_relationships() if not args.analyze_only else builder._build_networkx_graph()
            
            custom_results = test_join_paths(builder, custom_test_cases)
            logger.info(f"Custom tests: {custom_results['successful_paths']}/{custom_results['test_cases']} successful")
        
        logger.info("Relationship graph processing completed successfully!")
        
    except KeyboardInterrupt:
        logger.info("Operation cancelled by user")
        sys.exit(1)
    except Exception as e:
        logger.error(f"Error processing relationship graph: {e}", exc_info=args.verbose)
        sys.exit(1)

if __name__ == '__main__':
    main()