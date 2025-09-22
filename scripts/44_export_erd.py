#!/usr/bin/env python3
"""
Script 44: Export ERD
Export relationship graph in various formats (DOT, GraphML, Mermaid).
"""

import os
import sys
import argparse
import yaml
import logging
from datetime import datetime
from typing import Dict, Any, List, Set

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

class ERDExporter:
    """Export relationship graphs in various formats."""
    
    def __init__(self, builder: RelationshipBuilder, catalog: CatalogStore):
        self.builder = builder
        self.catalog = catalog
        self.graph = builder.graph
    
    def _get_table_info(self, table_key: str) -> Dict[str, Any]:
        """Get detailed information about a table."""
        if '.' not in table_key:
            return {"name": table_key, "columns": []}
        
        owner, table_name = table_key.split('.', 1)
        
        # Get table info
        with self.catalog._get_connection() as conn:
            # Get table details
            cursor = conn.execute("""
                SELECT num_rows, last_analyzed FROM tables
                WHERE owner = ? AND table_name = ?
            """, (owner, table_name))
            table_row = cursor.fetchone()
            
            # Get columns
            cursor = conn.execute("""
                SELECT column_name, data_type, nullable, is_pii
                FROM columns
                WHERE owner = ? AND table_name = ?
                ORDER BY column_name
            """, (owner, table_name))
            columns = [dict(row) for row in cursor.fetchall()]
            
            # Get table comment
            cursor = conn.execute("""
                SELECT comments FROM table_comments
                WHERE owner = ? AND table_name = ?
            """, (owner, table_name))
            comment_row = cursor.fetchone()
            comment = comment_row['comments'] if comment_row else None
        
        return {
            "owner": owner,
            "name": table_name,
            "full_name": table_key,
            "num_rows": table_row['num_rows'] if table_row else None,
            "last_analyzed": table_row['last_analyzed'] if table_row else None,
            "comment": comment,
            "columns": columns
        }
    
    def export_dot(self, output_file: str, include_columns: bool = True,
                  max_columns: int = 10) -> str:
        """
        Export graph as Graphviz DOT format.
        
        Args:
            output_file: Output file path
            include_columns: Whether to include column details
            max_columns: Maximum columns to show per table
            
        Returns:
            Generated DOT content
        """
        logger.info(f"Exporting DOT format to: {output_file}")
        
        dot_lines = [
            "digraph ERD {",
            "  rankdir=LR;",
            "  node [shape=record, fontname=\"Arial\"];",
            "  edge [fontname=\"Arial\", fontsize=10];",
            ""
        ]
        
        # Add table nodes
        for node_id in self.graph.nodes():
            table_info = self._get_table_info(node_id)
            
            # Build table label
            if include_columns and table_info['columns']:
                # Table header
                label_parts = [f"{{<title>{table_info['full_name']}|"]
                
                # Add columns (limited)
                columns_to_show = table_info['columns'][:max_columns]
                col_labels = []
                
                for col in columns_to_show:
                    col_label = f"{col['column_name']}: {col.get('data_type', 'Unknown')}"
                    if col.get('is_pii'):
                        col_label += " [PII]"
                    if col.get('nullable') == 'N':
                        col_label += " NOT NULL"
                    col_labels.append(col_label)
                
                if len(table_info['columns']) > max_columns:
                    col_labels.append(f"... ({len(table_info['columns']) - max_columns} more)")
                
                label_parts.append("\\l".join(col_labels))
                label_parts.append("}")
                label = "".join(label_parts) + "\\l"
            else:
                label = table_info['full_name']
            
            # Create safe node ID
            safe_node_id = node_id.replace('.', '_').replace('-', '_')
            
            dot_lines.append(f'  {safe_node_id} [label="{label}"];')
        
        dot_lines.append("")
        
        # Add edges (relationships)
        for source, target in self.graph.edges():
            edge_data = self.graph[source][target]
            
            safe_source = source.replace('.', '_').replace('-', '_')
            safe_target = target.replace('.', '_').replace('-', '_')
            
            # Build edge label
            cardinality = edge_data.get('cardinality', 'many_to_one')
            quality = edge_data.get('quality', 0)
            constraint = edge_data.get('constraint', '')
            
            edge_label = f"{cardinality}\\nQ:{quality:.2f}"
            if constraint:
                edge_label += f"\\n{constraint}"
            
            dot_lines.append(f'  {safe_source} -> {safe_target} [label="{edge_label}"];')
        
        dot_lines.append("}")
        
        dot_content = "\n".join(dot_lines)
        
        with open(output_file, 'w') as f:
            f.write(dot_content)
        
        logger.info(f"DOT export completed: {len(self.graph.nodes())} nodes, {len(self.graph.edges())} edges")
        return dot_content
    
    def export_graphml(self, output_file: str) -> str:
        """
        Export graph as GraphML format.
        
        Args:
            output_file: Output file path
            
        Returns:
            Generated GraphML content
        """
        logger.info(f"Exporting GraphML format to: {output_file}")
        
        graphml_lines = [
            '<?xml version="1.0" encoding="UTF-8"?>',
            '<graphml xmlns="http://graphml.graphdrawing.org/xmlns"',
            '         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"',
            '         xsi:schemaLocation="http://graphml.graphdrawing.org/xmlns',
            '         http://graphml.graphdrawing.org/xmlns/1.0/graphml.xsd">',
            '',
            '  <!-- Node attributes -->',
            '  <key id="owner" for="node" attr.name="owner" attr.type="string"/>',
            '  <key id="table_name" for="node" attr.name="table_name" attr.type="string"/>',
            '  <key id="num_rows" for="node" attr.name="num_rows" attr.type="int"/>',
            '  <key id="column_count" for="node" attr.name="column_count" attr.type="int"/>',
            '',
            '  <!-- Edge attributes -->',
            '  <key id="constraint_name" for="edge" attr.name="constraint_name" attr.type="string"/>',
            '  <key id="cardinality" for="edge" attr.name="cardinality" attr.type="string"/>',
            '  <key id="quality" for="edge" attr.name="quality" attr.type="double"/>',
            '',
            '  <graph id="ERD" edgedefault="directed">',
            ''
        ]
        
        # Add nodes
        for node_id in self.graph.nodes():
            table_info = self._get_table_info(node_id)
            safe_node_id = node_id.replace('.', '_').replace('-', '_')
            
            graphml_lines.extend([
                f'    <node id="{safe_node_id}">',
                f'      <data key="owner">{table_info.get("owner", "")}</data>',
                f'      <data key="table_name">{table_info.get("name", "")}</data>',
                f'      <data key="num_rows">{table_info.get("num_rows") or 0}</data>',
                f'      <data key="column_count">{len(table_info.get("columns", []))}</data>',
                f'    </node>',
                ''
            ])
        
        # Add edges
        for source, target in self.graph.edges():
            edge_data = self.graph[source][target]
            
            safe_source = source.replace('.', '_').replace('-', '_')
            safe_target = target.replace('.', '_').replace('-', '_')
            
            graphml_lines.extend([
                f'    <edge source="{safe_source}" target="{safe_target}">',
                f'      <data key="constraint_name">{edge_data.get("constraint", "")}</data>',
                f'      <data key="cardinality">{edge_data.get("cardinality", "")}</data>',
                f'      <data key="quality">{edge_data.get("quality", 0)}</data>',
                f'    </edge>',
                ''
            ])
        
        graphml_lines.extend([
            '  </graph>',
            '</graphml>'
        ])
        
        graphml_content = "\n".join(graphml_lines)
        
        with open(output_file, 'w') as f:
            f.write(graphml_content)
        
        logger.info(f"GraphML export completed: {len(self.graph.nodes())} nodes, {len(self.graph.edges())} edges")
        return graphml_content
    
    def export_mermaid(self, output_file: str, include_cardinality: bool = True) -> str:
        """
        Export graph as Mermaid diagram format.
        
        Args:
            output_file: Output file path
            include_cardinality: Whether to include cardinality labels
            
        Returns:
            Generated Mermaid content
        """
        logger.info(f"Exporting Mermaid format to: {output_file}")
        
        mermaid_lines = [
            "erDiagram",
            ""
        ]
        
        # Get all tables and their relationships
        tables_with_relationships = set()
        
        # Add relationship definitions
        for source, target in self.graph.edges():
            edge_data = self.graph[source][target]
            
            # Clean table names for Mermaid
            source_clean = source.replace('.', '_').replace('-', '_')
            target_clean = target.replace('.', '_').replace('-', '_')
            
            tables_with_relationships.add(source)
            tables_with_relationships.add(target)
            
            # Determine Mermaid relationship notation
            cardinality = edge_data.get('cardinality', 'many_to_one')
            
            if cardinality == 'one_to_one':
                relation = '||--||'
            elif cardinality == 'one_to_many':
                relation = '||--o{'
            elif cardinality == 'many_to_one':
                relation = '}o--||'
            else:  # many_to_many or unknown
                relation = '}o--o{'
            
            # Add relationship with optional label
            if include_cardinality:
                constraint = edge_data.get('constraint', '')
                quality = edge_data.get('quality', 0)
                label = f' : "{constraint} (Q:{quality:.2f})"' if constraint else f' : "Q:{quality:.2f}"'
            else:
                label = ""
            
            mermaid_lines.append(f"    {source_clean} {relation} {target_clean}{label}")
        
        mermaid_lines.append("")
        
        # Add table definitions with columns
        for table_key in sorted(tables_with_relationships):
            table_info = self._get_table_info(table_key)
            table_clean = table_key.replace('.', '_').replace('-', '_')
            
            mermaid_lines.append(f"    {table_clean} {{")
            
            # Add columns (limit for readability)
            columns_to_show = table_info['columns'][:8]  # Limit for readability
            
            for col in columns_to_show:
                col_type = col.get('data_type', 'Unknown')
                col_name = col['column_name']
                
                # Add type markers
                markers = []
                if col.get('nullable') == 'N':
                    markers.append('NOT NULL')
                if col.get('is_pii'):
                    markers.append('PII')
                
                marker_str = f" [{', '.join(markers)}]" if markers else ""
                
                mermaid_lines.append(f"        {col_type} {col_name}{marker_str}")
            
            if len(table_info['columns']) > 8:
                remaining = len(table_info['columns']) - 8
                mermaid_lines.append(f"        string ...{remaining}_more_columns")
            
            mermaid_lines.append("    }")
            mermaid_lines.append("")
        
        mermaid_content = "\n".join(mermaid_lines)
        
        with open(output_file, 'w') as f:
            f.write(mermaid_content)
        
        logger.info(f"Mermaid export completed: {len(tables_with_relationships)} tables, {len(self.graph.edges())} relationships")
        return mermaid_content

def export_all_formats(config: Dict[str, Any], formats: List[str]) -> Dict[str, str]:
    """
    Export relationship graph in all requested formats.
    
    Args:
        config: Database configuration
        formats: List of formats to export ('dot', 'graphml', 'mermaid')
        
    Returns:
        Dictionary mapping format names to output file paths
    """
    start_time = datetime.utcnow()
    
    # Setup catalog and builder
    catalog_path = config['catalog']['path']
    if not os.path.isabs(catalog_path):
        catalog_path = os.path.join(project_root, catalog_path)
    
    catalog = CatalogStore(catalog_path)
    builder = RelationshipBuilder(catalog)
    
    # Build the graph
    logger.info("Loading relationship graph...")
    builder.build_relationships()
    
    if builder.graph.number_of_nodes() == 0:
        raise ValueError("No relationship graph found. Run 43_build_aml_relgraph.py first.")
    
    # Setup output directory
    graphs_config = config.get('graphs', {})
    export_dir = graphs_config.get('export_dir', 'warehouse/graphs')
    
    if not os.path.isabs(export_dir):
        export_dir = os.path.join(project_root, export_dir)
    
    os.makedirs(export_dir, exist_ok=True)
    
    # Create exporter
    exporter = ERDExporter(builder, catalog)
    
    # Export in requested formats
    output_files = {}
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    
    for format_name in formats:
        if format_name == 'dot':
            output_file = os.path.join(export_dir, f"aml_erd_{timestamp}.dot")
            exporter.export_dot(output_file)
            output_files['dot'] = output_file
            
        elif format_name == 'graphml':
            output_file = os.path.join(export_dir, f"aml_erd_{timestamp}.graphml")
            exporter.export_graphml(output_file)
            output_files['graphml'] = output_file
            
        elif format_name == 'mermaid':
            output_file = os.path.join(export_dir, f"aml_erd_{timestamp}.mmd")
            exporter.export_mermaid(output_file)
            output_files['mermaid'] = output_file
            
        else:
            logger.warning(f"Unknown format: {format_name}")
    
    end_time = datetime.utcnow()
    duration = (end_time - start_time).total_seconds()
    
    logger.info(f"Export completed in {duration:.2f} seconds")
    return output_files

def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Export AML relationship graph in various formats",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Export in all formats
  python scripts/44_export_erd.py --fmt dot,graphml,mermaid
  
  # Export only DOT format
  python scripts/44_export_erd.py --fmt dot
  
  # Export with custom output directory
  python scripts/44_export_erd.py --fmt mermaid --output-dir "output/diagrams"
  
  # List available formats
  python scripts/44_export_erd.py --list-formats
        """
    )
    
    parser.add_argument(
        '--fmt', '--format',
        default='dot,graphml,mermaid',
        help='Comma-separated list of formats to export (dot,graphml,mermaid). Default: all'
    )
    parser.add_argument(
        '--output-dir',
        help='Output directory (overrides config)'
    )
    parser.add_argument(
        '--list-formats',
        action='store_true',
        help='List available export formats and exit'
    )
    parser.add_argument(
        '--verbose', '-v',
        action='store_true',
        help='Enable verbose logging'
    )
    
    args = parser.parse_args()
    
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)
    
    if args.list_formats:
        print("Available export formats:")
        print("  dot      - Graphviz DOT format (for graph visualization tools)")
        print("  graphml  - GraphML format (for analysis tools like Gephi)")
        print("  mermaid  - Mermaid diagram format (for documentation)")
        return
    
    try:
        # Parse formats
        formats = [f.strip().lower() for f in args.fmt.split(',')]
        valid_formats = {'dot', 'graphml', 'mermaid'}
        invalid_formats = set(formats) - valid_formats
        
        if invalid_formats:
            logger.error(f"Invalid formats: {', '.join(invalid_formats)}")
            logger.error(f"Valid formats: {', '.join(sorted(valid_formats))}")
            sys.exit(1)
        
        # Load configuration
        logger.info("Loading configuration...")
        config = load_config()
        
        # Override output directory if specified
        if args.output_dir:
            if 'graphs' not in config:
                config['graphs'] = {}
            config['graphs']['export_dir'] = args.output_dir
        
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
        
        if health['relationships'] == 0:
            logger.warning("No relationships found in catalog. Run 43_build_aml_relgraph.py first.")
        
        # Export in requested formats
        logger.info(f"Exporting ERD in formats: {', '.join(formats)}")
        output_files = export_all_formats(config, formats)
        
        logger.info("="*50)
        logger.info("EXPORT SUMMARY")
        logger.info("="*50)
        
        for format_name, output_file in output_files.items():
            file_size = os.path.getsize(output_file) if os.path.exists(output_file) else 0
            logger.info(f"{format_name.upper()}: {output_file} ({file_size} bytes)")
        
        logger.info("ERD export completed successfully!")
        
    except KeyboardInterrupt:
        logger.info("Operation cancelled by user")
        sys.exit(1)
    except Exception as e:
        logger.error(f"Error exporting ERD: {e}", exc_info=args.verbose)
        sys.exit(1)

if __name__ == '__main__':
    main()