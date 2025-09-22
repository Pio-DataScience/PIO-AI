"""
Relationship Graph Builder
Builds FK→PK relationship graphs with column mappings and cardinality detection.
"""
import json
import logging
from typing import Dict, List, Any, Optional, Tuple, Set
from dataclasses import dataclass, asdict
from collections import defaultdict, deque
import networkx as nx

from .catalog_store import CatalogStore

logger = logging.getLogger(__name__)

@dataclass
class ColumnMapping:
    """Mapping between FK and PK columns."""
    fk_column: str
    pk_column: str
    position: int
    data_type_match: bool = False
    nullable_match: bool = False

@dataclass
class Relationship:
    """A relationship between two tables via FK→PK."""
    fk_owner: str
    fk_table: str
    fk_constraint: str
    pk_owner: str
    pk_table: str
    pk_constraint: str
    edge_type: str = "FK_TO_PK"
    cardinality: str = "many_to_one"
    column_mappings: List[ColumnMapping] = None
    quality_score: float = 0.0
    
    def __post_init__(self):
        if self.column_mappings is None:
            self.column_mappings = []

@dataclass
class GraphNode:
    """A node in the relationship graph representing a table."""
    owner: str
    table_name: str
    node_id: str = None
    
    def __post_init__(self):
        if self.node_id is None:
            self.node_id = f"{self.owner}.{self.table_name}"

@dataclass
class JoinPath:
    """A path between two tables through FK relationships."""
    source_table: str
    target_table: str
    path_nodes: List[str]
    relationships: List[Relationship]
    total_quality: float
    path_length: int

class RelationshipBuilder:
    """Builds and manages relationship graphs from catalog metadata."""
    
    def __init__(self, catalog_store: CatalogStore):
        self.catalog = catalog_store
        self.graph = nx.DiGraph()
        self.relationships: Dict[str, Relationship] = {}
        
    def build_relationships(self) -> Dict[str, Any]:
        """Build all relationships from catalog constraints."""
        logger.info("Building relationships from catalog constraints")
        
        try:
            # Get all FK constraints and their referenced constraints
            with self.catalog._get_connection() as conn:
                cursor = conn.execute("""
                    SELECT c.owner, c.table_name, c.constraint_name, c.constraint_type,
                           c.r_owner, c.r_table, c.r_constraint
                    FROM constraints c
                    WHERE c.constraint_type = 'R'
                    AND c.r_owner IS NOT NULL 
                    AND c.r_table IS NOT NULL 
                    AND c.r_constraint IS NOT NULL
                    ORDER BY c.owner, c.table_name, c.constraint_name
                """)
                fk_constraints = [dict(row) for row in cursor.fetchall()]
            
            relationships_built = 0
            
            for fk_constraint in fk_constraints:
                try:
                    relationship = self._build_single_relationship(fk_constraint)
                    if relationship:
                        self._store_relationship(relationship)
                        relationships_built += 1
                except Exception as e:
                    logger.error(f"Error building relationship for constraint {fk_constraint['CONSTRAINT_NAME']}: {e}")
                    continue
            
            # Build the NetworkX graph
            self._build_networkx_graph()
            
            stats = {
                "total_relationships": relationships_built,
                "graph_nodes": self.graph.number_of_nodes(),
                "graph_edges": self.graph.number_of_edges(),
                "strongly_connected_components": len(list(nx.strongly_connected_components(self.graph))),
                "weakly_connected_components": len(list(nx.weakly_connected_components(self.graph)))
            }
            
            logger.info(f"Built relationship graph: {stats}")
            return stats
            
        except Exception as e:
            logger.error(f"Error building relationships: {e}")
            raise
    
    def _build_single_relationship(self, fk_constraint: Dict[str, Any]) -> Optional[Relationship]:
        """Build a single relationship from FK constraint data."""
        fk_owner = fk_constraint['OWNER']
        fk_table = fk_constraint['TABLE_NAME']
        fk_constraint_name = fk_constraint['CONSTRAINT_NAME']
        pk_owner = fk_constraint['R_OWNER']
        pk_table = fk_constraint['R_TABLE']
        pk_constraint_name = fk_constraint['R_CONSTRAINT']
        
        logger.debug(f"Building relationship: {fk_owner}.{fk_table}.{fk_constraint_name} -> {pk_owner}.{pk_table}.{pk_constraint_name}")
        
        try:
            # Get FK columns
            fk_columns = self._get_constraint_columns(fk_owner, fk_constraint_name, fk_table)
            
            # Get PK columns
            pk_columns = self._get_constraint_columns(pk_owner, pk_constraint_name, pk_table)
            
            if not fk_columns or not pk_columns:
                logger.warning(f"No columns found for relationship {fk_constraint_name}")
                return None
            
            # Build column mappings
            column_mappings = self._build_column_mappings(
                fk_owner, fk_table, fk_columns,
                pk_owner, pk_table, pk_columns
            )
            
            # Determine cardinality
            cardinality = self._determine_cardinality(fk_owner, fk_table, fk_columns)
            
            # Calculate quality score
            quality_score = self._calculate_quality_score(column_mappings)
            
            relationship = Relationship(
                fk_owner=fk_owner,
                fk_table=fk_table,
                fk_constraint=fk_constraint_name,
                pk_owner=pk_owner,
                pk_table=pk_table,
                pk_constraint=pk_constraint_name,
                cardinality=cardinality,
                column_mappings=column_mappings,
                quality_score=quality_score
            )
            
            return relationship
            
        except Exception as e:
            logger.error(f"Error building single relationship: {e}")
            return None
    
    def _get_constraint_columns(self, owner: str, constraint_name: str, table_name: str) -> List[Dict[str, Any]]:
        """Get columns for a constraint in order."""
        with self.catalog._get_connection() as conn:
            cursor = conn.execute("""
                SELECT column_name, position
                FROM cons_columns
                WHERE owner = ? AND constraint_name = ? AND table_name = ?
                ORDER BY position
            """, (owner, constraint_name, table_name))
            return [dict(row) for row in cursor.fetchall()]
    
    def _get_column_details(self, owner: str, table_name: str, column_name: str) -> Optional[Dict[str, Any]]:
        """Get detailed column information."""
        with self.catalog._get_connection() as conn:
            cursor = conn.execute("""
                SELECT data_type, data_length, data_precision, data_scale, nullable
                FROM columns
                WHERE owner = ? AND table_name = ? AND column_name = ?
            """, (owner, table_name, column_name))
            row = cursor.fetchone()
            return dict(row) if row else None
    
    def _build_column_mappings(self, 
                             fk_owner: str, fk_table: str, fk_columns: List[Dict[str, Any]],
                             pk_owner: str, pk_table: str, pk_columns: List[Dict[str, Any]]) -> List[ColumnMapping]:
        """Build column mappings between FK and PK columns."""
        mappings = []
        
        # Pair columns by position
        for i, (fk_col, pk_col) in enumerate(zip(fk_columns, pk_columns)):
            fk_column_name = fk_col['COLUMN_NAME']
            pk_column_name = pk_col['COLUMN_NAME']
            position = fk_col['POSITION']
            
            # Get detailed column information
            fk_details = self._get_column_details(fk_owner, fk_table, fk_column_name)
            pk_details = self._get_column_details(pk_owner, pk_table, pk_column_name)
            
            # Check data type compatibility
            data_type_match = False
            nullable_match = False
            
            if fk_details and pk_details:
                data_type_match = (
                    fk_details.get('DATA_TYPE') == pk_details.get('DATA_TYPE') and
                    fk_details.get('DATA_LENGTH') == pk_details.get('DATA_LENGTH') and
                    fk_details.get('DATA_PRECISION') == pk_details.get('DATA_PRECISION') and
                    fk_details.get('DATA_SCALE') == pk_details.get('DATA_SCALE')
                )
                nullable_match = fk_details.get('NULLABLE') == pk_details.get('NULLABLE')
            
            mapping = ColumnMapping(
                fk_column=fk_column_name,
                pk_column=pk_column_name,
                position=position,
                data_type_match=data_type_match,
                nullable_match=nullable_match
            )
            mappings.append(mapping)
        
        return mappings
    
    def _determine_cardinality(self, fk_owner: str, fk_table: str, fk_columns: List[Dict[str, Any]]) -> str:
        """Determine relationship cardinality."""
        # Default to many-to-one (most common for FK relationships)
        cardinality = "many_to_one"
        
        try:
            # Check if FK columns form a unique constraint
            fk_column_names = [col['COLUMN_NAME'] for col in fk_columns]
            
            # Look for unique constraints on these exact columns
            with self.catalog._get_connection() as conn:
                # Build a query to check for unique constraints covering these columns
                placeholders = ','.join(['?' for _ in fk_column_names])
                cursor = conn.execute(f"""
                    SELECT c.constraint_name, COUNT(*) as col_count
                    FROM constraints c
                    JOIN cons_columns cc ON c.owner = cc.owner 
                        AND c.constraint_name = cc.constraint_name
                        AND c.table_name = cc.table_name
                    WHERE c.owner = ? AND c.table_name = ?
                    AND c.constraint_type IN ('U', 'P')
                    AND cc.column_name IN ({placeholders})
                    GROUP BY c.constraint_name
                    HAVING COUNT(*) = ?
                """, [fk_owner, fk_table] + fk_column_names + [len(fk_column_names)])
                
                unique_constraints = cursor.fetchall()
                if unique_constraints:
                    cardinality = "one_to_one"
            
        except Exception as e:
            logger.debug(f"Error determining cardinality for {fk_owner}.{fk_table}: {e}")
        
        return cardinality
    
    def _calculate_quality_score(self, column_mappings: List[ColumnMapping]) -> float:
        """Calculate relationship quality score based on column compatibility."""
        if not column_mappings:
            return 0.0
        
        total_score = 0.0
        
        for mapping in column_mappings:
            mapping_score = 0.5  # Base score for having a mapping
            
            if mapping.data_type_match:
                mapping_score += 0.3
            
            if mapping.nullable_match:
                mapping_score += 0.2
            
            total_score += mapping_score
        
        # Average score across all mappings
        quality_score = total_score / len(column_mappings)
        
        return round(quality_score, 3)
    
    def _store_relationship(self, relationship: Relationship) -> None:
        """Store relationship in catalog and local cache."""
        # Convert column mappings to JSON
        colmap_dict = [asdict(mapping) for mapping in relationship.column_mappings]
        
        # Store in catalog
        self.catalog.upsert_relationship(
            fk_owner=relationship.fk_owner,
            fk_table=relationship.fk_table,
            fk_constraint=relationship.fk_constraint,
            pk_owner=relationship.pk_owner,
            pk_table=relationship.pk_table,
            pk_constraint=relationship.pk_constraint,
            edge_type=relationship.edge_type,
            cardinality=relationship.cardinality,
            colmap=colmap_dict,
            quality=relationship.quality_score
        )
        
        # Store in local cache
        rel_key = f"{relationship.fk_owner}.{relationship.fk_table}.{relationship.fk_constraint}"
        self.relationships[rel_key] = relationship
    
    def _build_networkx_graph(self) -> None:
        """Build NetworkX graph from relationships."""
        self.graph.clear()
        
        # Add all relationships to graph
        for relationship in self.relationships.values():
            fk_node = f"{relationship.fk_owner}.{relationship.fk_table}"
            pk_node = f"{relationship.pk_owner}.{relationship.pk_table}"
            
            # Add nodes if not exists
            if not self.graph.has_node(fk_node):
                self.graph.add_node(fk_node, 
                                  owner=relationship.fk_owner, 
                                  table=relationship.fk_table)
            
            if not self.graph.has_node(pk_node):
                self.graph.add_node(pk_node, 
                                  owner=relationship.pk_owner, 
                                  table=relationship.pk_table)
            
            # Add edge
            self.graph.add_edge(fk_node, pk_node,
                              constraint=relationship.fk_constraint,
                              cardinality=relationship.cardinality,
                              quality=relationship.quality_score,
                              column_mappings=relationship.column_mappings)
    
    def find_join_path(self, source_table: str, target_table: str, 
                      max_path_length: int = 5) -> Optional[JoinPath]:
        """
        Find shortest join path between two tables.
        
        Args:
            source_table: Source table in format "OWNER.TABLE"
            target_table: Target table in format "OWNER.TABLE"
            max_path_length: Maximum path length to search
            
        Returns:
            JoinPath object if path found, None otherwise
        """
        if source_table not in self.graph or target_table not in self.graph:
            return None
        
        try:
            # Use NetworkX to find shortest path (undirected for join paths)
            undirected_graph = self.graph.to_undirected()
            
            path_nodes = nx.shortest_path(undirected_graph, source_table, target_table)
            
            if len(path_nodes) - 1 > max_path_length:
                logger.debug(f"Path too long: {len(path_nodes) - 1} > {max_path_length}")
                return None
            
            # Build relationships along the path
            path_relationships = []
            total_quality = 0.0
            
            for i in range(len(path_nodes) - 1):
                from_node = path_nodes[i]
                to_node = path_nodes[i + 1]
                
                # Find the relationship (check both directions)
                edge_data = None
                if self.graph.has_edge(from_node, to_node):
                    edge_data = self.graph[from_node][to_node]
                elif self.graph.has_edge(to_node, from_node):
                    edge_data = self.graph[to_node][from_node]
                    # Swap nodes for correct direction
                    from_node, to_node = to_node, from_node
                
                if edge_data:
                    # Find the full relationship object
                    constraint_name = edge_data['constraint']
                    relationship = None
                    
                    for rel in self.relationships.values():
                        if rel.fk_constraint == constraint_name:
                            relationship = rel
                            break
                    
                    if relationship:
                        path_relationships.append(relationship)
                        total_quality += relationship.quality_score
            
            if path_relationships:
                avg_quality = total_quality / len(path_relationships)
                
                return JoinPath(
                    source_table=source_table,
                    target_table=target_table,
                    path_nodes=path_nodes,
                    relationships=path_relationships,
                    total_quality=round(avg_quality, 3),
                    path_length=len(path_nodes) - 1
                )
        
        except nx.NetworkXNoPath:
            logger.debug(f"No path found between {source_table} and {target_table}")
        except Exception as e:
            logger.error(f"Error finding join path: {e}")
        
        return None
    
    def get_table_relationships(self, owner: str, table_name: str) -> Dict[str, List[Relationship]]:
        """Get all relationships for a specific table."""
        table_key = f"{owner}.{table_name}"
        
        incoming = []  # Tables that reference this table
        outgoing = []  # Tables that this table references
        
        for relationship in self.relationships.values():
            fk_table_key = f"{relationship.fk_owner}.{relationship.fk_table}"
            pk_table_key = f"{relationship.pk_owner}.{relationship.pk_table}"
            
            if pk_table_key == table_key:
                incoming.append(relationship)
            elif fk_table_key == table_key:
                outgoing.append(relationship)
        
        return {
            "incoming": incoming,
            "outgoing": outgoing
        }
    
    def export_graph_data(self) -> Dict[str, Any]:
        """Export graph data for visualization and analysis."""
        nodes = []
        edges = []
        
        for node_id in self.graph.nodes():
            node_data = self.graph.nodes[node_id]
            nodes.append({
                "id": node_id,
                "owner": node_data.get("owner"),
                "table": node_data.get("table"),
                "in_degree": self.graph.in_degree(node_id),
                "out_degree": self.graph.out_degree(node_id)
            })
        
        for source, target in self.graph.edges():
            edge_data = self.graph[source][target]
            edges.append({
                "source": source,
                "target": target,
                "constraint": edge_data.get("constraint"),
                "cardinality": edge_data.get("cardinality"),
                "quality": edge_data.get("quality")
            })
        
        return {
            "nodes": nodes,
            "edges": edges,
            "graph_stats": {
                "node_count": len(nodes),
                "edge_count": len(edges),
                "density": nx.density(self.graph),
                "is_connected": nx.is_weakly_connected(self.graph)
            }
        }