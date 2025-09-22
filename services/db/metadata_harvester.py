"""
Oracle Metadata Harvester
Harvests metadata from Oracle database using DBA_* views with AML domain focus.
"""
import logging
from typing import List, Dict, Any, Optional
from dataclasses import dataclass
from .oracle_conn import safe_execute_query
from .catalog_store import CatalogStore
from .classifiers import PIIClassifier

logger = logging.getLogger(__name__)

@dataclass
class HarvestConfig:
    """Configuration for metadata harvesting."""
    owners: List[str]
    name_patterns: List[str]
    exclude_patterns: List[str]
    use_dba_views: bool = True
    batch_size: int = 1000

class MetadataHarvester:
    """Harvests Oracle metadata for AML domain."""
    
    def __init__(self, config: HarvestConfig, catalog_store: CatalogStore):
        self.config = config
        self.catalog = catalog_store
        self.pii_classifier = PIIClassifier()
        
        # Query templates - using DBA_* views with ALL_* fallback
        self.view_prefix = "DBA_" if config.use_dba_views else "ALL_"
        
    def _get_tables_query(self) -> str:
        """Get SQL query for tables metadata."""
        return f"""
            SELECT owner, table_name, num_rows, last_analyzed
            FROM {self.view_prefix}TABLES
            WHERE owner = :owner
            ORDER BY owner, table_name
        """
    
    def _get_tables_by_pattern_query(self) -> str:
        """Get SQL query for tables by name pattern."""
        return f"""
            SELECT owner, table_name, num_rows, last_analyzed
            FROM {self.view_prefix}TABLES
            WHERE table_name LIKE :pattern
            AND owner NOT IN ('SYS', 'SYSTEM', 'SYSAUX', 'OUTLN', 'DBSNMP')
            ORDER BY owner, table_name
        """
    
    def _get_views_query(self) -> str:
        """Get SQL query for views metadata."""
        return f"""
            SELECT owner, view_name, text
            FROM {self.view_prefix}VIEWS
            WHERE owner = :owner
            ORDER BY owner, view_name
        """
    
    def _get_views_by_pattern_query(self) -> str:
        """Get SQL query for views by name pattern."""
        return f"""
            SELECT owner, view_name, text
            FROM {self.view_prefix}VIEWS
            WHERE view_name LIKE :pattern
            AND owner NOT IN ('SYS', 'SYSTEM', 'SYSAUX', 'OUTLN', 'DBSNMP')
            ORDER BY owner, view_name
        """
    
    def _get_columns_query(self) -> str:
        """Get SQL query for columns metadata."""
        return f"""
            SELECT owner, table_name, column_name, data_type, 
                   data_length, data_precision, data_scale, 
                   nullable, data_default
            FROM {self.view_prefix}TAB_COLUMNS
            WHERE owner = :owner AND table_name = :table_name
            ORDER BY column_id
        """
    
    def _get_table_comments_query(self) -> str:
        """Get SQL query for table comments."""
        return f"""
            SELECT owner, table_name, comments
            FROM {self.view_prefix}TAB_COMMENTS
            WHERE owner = :owner AND table_name = :table_name
            AND comments IS NOT NULL
        """
    
    def _get_column_comments_query(self) -> str:
        """Get SQL query for column comments."""
        return f"""
            SELECT owner, table_name, column_name, comments
            FROM {self.view_prefix}COL_COMMENTS
            WHERE owner = :owner AND table_name = :table_name
            AND comments IS NOT NULL
        """
    
    def _get_constraints_query(self) -> str:
        """Get SQL query for constraints metadata."""
        return f"""
            SELECT c.owner, c.table_name, c.constraint_name, c.constraint_type,
                   r.owner r_owner, r.table_name r_table, r.constraint_name r_constraint
            FROM {self.view_prefix}CONSTRAINTS c
            LEFT JOIN {self.view_prefix}CONSTRAINTS r
                ON c.r_constraint_name = r.constraint_name 
                AND c.r_owner = r.owner
            WHERE c.owner = :owner AND c.table_name = :table_name
            AND c.constraint_type IN ('P', 'R', 'U', 'C')
            ORDER BY c.constraint_type, c.constraint_name
        """
    
    def _get_constraint_columns_query(self) -> str:
        """Get SQL query for constraint columns."""
        return f"""
            SELECT owner, constraint_name, table_name, column_name, position
            FROM {self.view_prefix}CONS_COLUMNS
            WHERE owner = :owner AND table_name = :table_name
            ORDER BY constraint_name, position
        """
    
    def _get_dependencies_query(self) -> str:
        """Get SQL query for object dependencies."""
        return f"""
            SELECT owner, name, type, 
                   referenced_owner ref_owner, 
                   referenced_name ref_name,
                   referenced_type ref_type
            FROM {self.view_prefix}DEPENDENCIES
            WHERE (owner = :owner AND name = :name)
               OR (referenced_owner = :owner AND referenced_name = :name)
        """
    
    def _should_exclude_table(self, table_name: str) -> bool:
        """Check if table should be excluded based on patterns."""
        table_upper = table_name.upper()
        
        for pattern in self.config.exclude_patterns:
            if pattern.replace('%', '') in table_upper:
                return True
        return False
    
    def harvest_tables_by_owner(self, owner: str) -> int:
        """Harvest tables for a specific owner."""
        logger.info(f"Harvesting tables for owner: {owner}")
        
        try:
            # Upsert schema
            self.catalog.upsert_schema(owner)
            
            # Get tables
            tables = safe_execute_query(
                self._get_tables_query(),
                {"owner": owner}
            )
            
            harvested_count = 0
            for table in tables:
                table_name = table['TABLE_NAME']
                
                if self._should_exclude_table(table_name):
                    logger.debug(f"Excluding table {owner}.{table_name} (matches exclude pattern)")
                    continue
                
                # Store table metadata
                self.catalog.upsert_table(
                    owner=owner,
                    table_name=table_name,
                    num_rows=table.get('NUM_ROWS'),
                    last_analyzed=table.get('LAST_ANALYZED')
                )
                
                # Harvest detailed metadata for this table
                self._harvest_table_details(owner, table_name)
                harvested_count += 1
            
            logger.info(f"Harvested {harvested_count} tables for owner {owner}")
            return harvested_count
            
        except Exception as e:
            logger.error(f"Error harvesting tables for owner {owner}: {e}")
            raise
    
    def harvest_tables_by_pattern(self, pattern: str) -> int:
        """Harvest tables matching a pattern."""
        logger.info(f"Harvesting tables matching pattern: {pattern}")
        
        try:
            tables = safe_execute_query(
                self._get_tables_by_pattern_query(),
                {"pattern": pattern}
            )
            
            harvested_count = 0
            processed_owners = set()
            
            for table in tables:
                owner = table['OWNER']
                table_name = table['TABLE_NAME']
                
                if self._should_exclude_table(table_name):
                    logger.debug(f"Excluding table {owner}.{table_name} (matches exclude pattern)")
                    continue
                
                # Ensure schema exists
                if owner not in processed_owners:
                    self.catalog.upsert_schema(owner)
                    processed_owners.add(owner)
                
                # Store table metadata
                self.catalog.upsert_table(
                    owner=owner,
                    table_name=table_name,
                    num_rows=table.get('NUM_ROWS'),
                    last_analyzed=table.get('LAST_ANALYZED')
                )
                
                # Harvest detailed metadata for this table
                self._harvest_table_details(owner, table_name)
                harvested_count += 1
            
            logger.info(f"Harvested {harvested_count} tables matching pattern {pattern}")
            return harvested_count
            
        except Exception as e:
            logger.error(f"Error harvesting tables for pattern {pattern}: {e}")
            raise
    
    def harvest_views_by_owner(self, owner: str) -> int:
        """Harvest views for a specific owner."""
        logger.info(f"Harvesting views for owner: {owner}")
        
        try:
            views = safe_execute_query(
                self._get_views_query(),
                {"owner": owner}
            )
            
            for view in views:
                view_name = view['VIEW_NAME']
                
                if self._should_exclude_table(view_name):  # Use same exclusion logic
                    logger.debug(f"Excluding view {owner}.{view_name} (matches exclude pattern)")
                    continue
                
                # Store view metadata
                self.catalog.upsert_view(
                    owner=owner,
                    view_name=view_name,
                    text=view.get('TEXT')
                )
                
                # Harvest columns for this view (views have columns too)
                self._harvest_columns(owner, view_name)
            
            logger.info(f"Harvested {len(views)} views for owner {owner}")
            return len(views)
            
        except Exception as e:
            logger.error(f"Error harvesting views for owner {owner}: {e}")
            raise
    
    def harvest_views_by_pattern(self, pattern: str) -> int:
        """Harvest views matching a pattern."""
        logger.info(f"Harvesting views matching pattern: {pattern}")
        
        try:
            views = safe_execute_query(
                self._get_views_by_pattern_query(),
                {"pattern": pattern}
            )
            
            processed_owners = set()
            
            for view in views:
                owner = view['OWNER']
                view_name = view['VIEW_NAME']
                
                if self._should_exclude_table(view_name):
                    logger.debug(f"Excluding view {owner}.{view_name} (matches exclude pattern)")
                    continue
                
                # Ensure schema exists
                if owner not in processed_owners:
                    self.catalog.upsert_schema(owner)
                    processed_owners.add(owner)
                
                # Store view metadata
                self.catalog.upsert_view(
                    owner=owner,
                    view_name=view_name,
                    text=view.get('TEXT')
                )
                
                # Harvest columns for this view
                self._harvest_columns(owner, view_name)
            
            logger.info(f"Harvested {len(views)} views matching pattern {pattern}")
            return len(views)
            
        except Exception as e:
            logger.error(f"Error harvesting views for pattern {pattern}: {e}")
            raise
    
    def _harvest_table_details(self, owner: str, table_name: str) -> None:
        """Harvest detailed metadata for a specific table."""
        logger.debug(f"Harvesting details for {owner}.{table_name}")
        
        # Harvest columns
        self._harvest_columns(owner, table_name)
        
        # Harvest comments
        self._harvest_comments(owner, table_name)
        
        # Harvest constraints
        self._harvest_constraints(owner, table_name)
        
        # Harvest dependencies
        self._harvest_dependencies(owner, table_name)
    
    def _harvest_columns(self, owner: str, table_name: str) -> None:
        """Harvest column metadata for a table/view."""
        try:
            columns = safe_execute_query(
                self._get_columns_query(),
                {"owner": owner, "table_name": table_name}
            )
            
            for column in columns:
                column_name = column['COLUMN_NAME']
                
                # Classify PII
                is_pii = self.pii_classifier.is_pii(column_name)
                
                self.catalog.upsert_column(
                    owner=owner,
                    table_name=table_name,
                    column_name=column_name,
                    data_type=column.get('DATA_TYPE'),
                    data_length=column.get('DATA_LENGTH'),
                    data_precision=column.get('DATA_PRECISION'),
                    data_scale=column.get('DATA_SCALE'),
                    nullable=column.get('NULLABLE'),
                    data_default=column.get('DATA_DEFAULT'),
                    is_pii=is_pii
                )
                
        except Exception as e:
            logger.error(f"Error harvesting columns for {owner}.{table_name}: {e}")
    
    def _harvest_comments(self, owner: str, table_name: str) -> None:
        """Harvest comment metadata for a table."""
        try:
            # Table comments
            table_comments = safe_execute_query(
                self._get_table_comments_query(),
                {"owner": owner, "table_name": table_name}
            )
            
            for comment in table_comments:
                self.catalog.upsert_table_comment(
                    owner=owner,
                    table_name=table_name,
                    comments=comment.get('COMMENTS')
                )
            
            # Column comments
            column_comments = safe_execute_query(
                self._get_column_comments_query(),
                {"owner": owner, "table_name": table_name}
            )
            
            for comment in column_comments:
                self.catalog.upsert_column_comment(
                    owner=owner,
                    table_name=table_name,
                    column_name=comment['COLUMN_NAME'],
                    comments=comment.get('COMMENTS')
                )
                
        except Exception as e:
            logger.error(f"Error harvesting comments for {owner}.{table_name}: {e}")
    
    def _harvest_constraints(self, owner: str, table_name: str) -> None:
        """Harvest constraint metadata for a table."""
        try:
            constraints = safe_execute_query(
                self._get_constraints_query(),
                {"owner": owner, "table_name": table_name}
            )
            
            for constraint in constraints:
                self.catalog.upsert_constraint(
                    owner=owner,
                    table_name=table_name,
                    constraint_name=constraint['CONSTRAINT_NAME'],
                    constraint_type=constraint['CONSTRAINT_TYPE'],
                    r_owner=constraint.get('R_OWNER'),
                    r_table=constraint.get('R_TABLE'),
                    r_constraint=constraint.get('R_CONSTRAINT')
                )
            
            # Constraint columns
            constraint_columns = safe_execute_query(
                self._get_constraint_columns_query(),
                {"owner": owner, "table_name": table_name}
            )
            
            for cons_col in constraint_columns:
                self.catalog.upsert_constraint_column(
                    owner=owner,
                    constraint_name=cons_col['CONSTRAINT_NAME'],
                    table_name=table_name,
                    column_name=cons_col['COLUMN_NAME'],
                    position=cons_col.get('POSITION', 1)
                )
                
        except Exception as e:
            logger.error(f"Error harvesting constraints for {owner}.{table_name}: {e}")
    
    def _harvest_dependencies(self, owner: str, table_name: str) -> None:
        """Harvest dependency metadata for a table."""
        try:
            dependencies = safe_execute_query(
                self._get_dependencies_query(),
                {"owner": owner, "name": table_name}
            )
            
            for dep in dependencies:
                self.catalog.upsert_dependency(
                    owner=dep['OWNER'],
                    name=dep['NAME'],
                    type_=dep['TYPE'],
                    ref_owner=dep['REF_OWNER'],
                    ref_name=dep['REF_NAME'],
                    ref_type=dep['REF_TYPE']
                )
                
        except Exception as e:
            logger.error(f"Error harvesting dependencies for {owner}.{table_name}: {e}")
    
    def harvest_aml_metadata(self) -> Dict[str, int]:
        """Harvest metadata for AML domain using configured patterns."""
        logger.info("Starting AML metadata harvest")
        
        stats = {
            "tables_by_owner": 0,
            "tables_by_pattern": 0,
            "views_by_owner": 0,
            "views_by_pattern": 0,
            "total_objects": 0
        }
        
        try:
            # Harvest by owners
            for owner in self.config.owners:
                stats["tables_by_owner"] += self.harvest_tables_by_owner(owner)
                stats["views_by_owner"] += self.harvest_views_by_owner(owner)
            
            # Harvest by patterns
            for pattern in self.config.name_patterns:
                stats["tables_by_pattern"] += self.harvest_tables_by_pattern(pattern)
                stats["views_by_pattern"] += self.harvest_views_by_pattern(pattern)
            
            stats["total_objects"] = (
                stats["tables_by_owner"] + stats["tables_by_pattern"] +
                stats["views_by_owner"] + stats["views_by_pattern"]
            )
            
            logger.info(f"AML metadata harvest completed: {stats}")
            return stats
            
        except Exception as e:
            logger.error(f"Error during AML metadata harvest: {e}")
            raise