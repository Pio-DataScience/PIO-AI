"""
SQLite Catalog Store for Oracle Metadata
Manages catalog database schema and provides idempotent operations.
"""
import sqlite3
import json
import logging
from pathlib import Path
from typing import List, Dict, Any, Optional, Union
from contextlib import contextmanager
from datetime import datetime

logger = logging.getLogger(__name__)

class CatalogStore:
    """SQLite catalog store for Oracle metadata with idempotent operations."""
    
    def __init__(self, db_path: str):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()
    
    def _init_schema(self):
        """Initialize the catalog database schema."""
        with self._get_connection() as conn:
            # Schemas table
            conn.execute("""
                CREATE TABLE IF NOT EXISTS schemas (
                    owner TEXT PRIMARY KEY,
                    created_date TEXT DEFAULT CURRENT_TIMESTAMP,
                    last_updated TEXT DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # Tables table
            conn.execute("""
                CREATE TABLE IF NOT EXISTS tables (
                    owner TEXT NOT NULL,
                    table_name TEXT NOT NULL,
                    num_rows INTEGER,
                    last_analyzed TEXT,
                    created_date TEXT DEFAULT CURRENT_TIMESTAMP,
                    last_updated TEXT DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (owner, table_name)
                )
            """)
            
            # Views table
            conn.execute("""
                CREATE TABLE IF NOT EXISTS views (
                    owner TEXT NOT NULL,
                    view_name TEXT NOT NULL,
                    text TEXT,
                    created_date TEXT DEFAULT CURRENT_TIMESTAMP,
                    last_updated TEXT DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (owner, view_name)
                )
            """)
            
            # Columns table
            conn.execute("""
                CREATE TABLE IF NOT EXISTS columns (
                    owner TEXT NOT NULL,
                    table_name TEXT NOT NULL,
                    column_name TEXT NOT NULL,
                    data_type TEXT,
                    data_length INTEGER,
                    data_precision INTEGER,
                    data_scale INTEGER,
                    nullable TEXT,
                    data_default TEXT,
                    is_pii BOOLEAN DEFAULT 0,
                    created_date TEXT DEFAULT CURRENT_TIMESTAMP,
                    last_updated TEXT DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (owner, table_name, column_name)
                )
            """)
            
            # Table comments
            conn.execute("""
                CREATE TABLE IF NOT EXISTS table_comments (
                    owner TEXT NOT NULL,
                    table_name TEXT NOT NULL,
                    comments TEXT,
                    created_date TEXT DEFAULT CURRENT_TIMESTAMP,
                    last_updated TEXT DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (owner, table_name)
                )
            """)
            
            # Column comments
            conn.execute("""
                CREATE TABLE IF NOT EXISTS column_comments (
                    owner TEXT NOT NULL,
                    table_name TEXT NOT NULL,
                    column_name TEXT NOT NULL,
                    comments TEXT,
                    created_date TEXT DEFAULT CURRENT_TIMESTAMP,
                    last_updated TEXT DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (owner, table_name, column_name)
                )
            """)
            
            # Constraints table
            conn.execute("""
                CREATE TABLE IF NOT EXISTS constraints (
                    owner TEXT NOT NULL,
                    table_name TEXT NOT NULL,
                    constraint_name TEXT NOT NULL,
                    constraint_type TEXT,
                    r_owner TEXT,
                    r_table TEXT,
                    r_constraint TEXT,
                    created_date TEXT DEFAULT CURRENT_TIMESTAMP,
                    last_updated TEXT DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (owner, table_name, constraint_name)
                )
            """)
            
            # Constraint columns
            conn.execute("""
                CREATE TABLE IF NOT EXISTS cons_columns (
                    owner TEXT NOT NULL,
                    constraint_name TEXT NOT NULL,
                    table_name TEXT NOT NULL,
                    column_name TEXT NOT NULL,
                    position INTEGER,
                    created_date TEXT DEFAULT CURRENT_TIMESTAMP,
                    last_updated TEXT DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (owner, constraint_name, table_name, column_name)
                )
            """)
            
            # Relationships table
            conn.execute("""
                CREATE TABLE IF NOT EXISTS relationships (
                    fk_owner TEXT NOT NULL,
                    fk_table TEXT NOT NULL,
                    fk_constraint TEXT NOT NULL,
                    pk_owner TEXT NOT NULL,
                    pk_table TEXT NOT NULL,
                    pk_constraint TEXT NOT NULL,
                    edge_type TEXT DEFAULT 'FK_TO_PK',
                    cardinality TEXT,
                    colmap_json TEXT,
                    quality REAL,
                    created_date TEXT DEFAULT CURRENT_TIMESTAMP,
                    last_updated TEXT DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (fk_owner, fk_table, fk_constraint, pk_owner, pk_table, pk_constraint)
                )
            """)
            
            # Dependencies table
            conn.execute("""
                CREATE TABLE IF NOT EXISTS dependencies (
                    owner TEXT NOT NULL,
                    name TEXT NOT NULL,
                    type TEXT NOT NULL,
                    ref_owner TEXT NOT NULL,
                    ref_name TEXT NOT NULL,
                    ref_type TEXT NOT NULL,
                    created_date TEXT DEFAULT CURRENT_TIMESTAMP,
                    last_updated TEXT DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (owner, name, type, ref_owner, ref_name, ref_type)
                )
            """)
            
            # Catalog embeddings table
            conn.execute("""
                CREATE TABLE IF NOT EXISTS catalog_embeddings (
                    entity_type TEXT NOT NULL,
                    owner TEXT NOT NULL,
                    name TEXT NOT NULL,
                    extra TEXT,
                    vector BLOB,
                    created_date TEXT DEFAULT CURRENT_TIMESTAMP,
                    last_updated TEXT DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (entity_type, owner, name, extra)
                )
            """)
            
            # Create indexes for better performance
            indexes = [
                "CREATE INDEX IF NOT EXISTS idx_tables_owner ON tables(owner)",
                "CREATE INDEX IF NOT EXISTS idx_columns_table ON columns(owner, table_name)",
                "CREATE INDEX IF NOT EXISTS idx_constraints_type ON constraints(constraint_type)",
                "CREATE INDEX IF NOT EXISTS idx_relationships_fk ON relationships(fk_owner, fk_table)",
                "CREATE INDEX IF NOT EXISTS idx_relationships_pk ON relationships(pk_owner, pk_table)",
                "CREATE INDEX IF NOT EXISTS idx_dependencies_ref ON dependencies(ref_owner, ref_name)",
                "CREATE INDEX IF NOT EXISTS idx_embeddings_type ON catalog_embeddings(entity_type)"
            ]
            
            for idx in indexes:
                conn.execute(idx)
            
            conn.commit()
            logger.info("Catalog database schema initialized")
    
    @contextmanager
    def _get_connection(self):
        """Get a database connection with proper error handling."""
        conn = None
        try:
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            yield conn
        except Exception as e:
            if conn:
                conn.rollback()
            logger.error(f"Database error: {e}")
            raise
        finally:
            if conn:
                conn.close()
    
    def upsert_schema(self, owner: str) -> None:
        """Insert or update schema record."""
        with self._get_connection() as conn:
            conn.execute("""
                INSERT OR REPLACE INTO schemas (owner, last_updated)
                VALUES (?, CURRENT_TIMESTAMP)
            """, (owner,))
            conn.commit()
    
    def upsert_table(self, owner: str, table_name: str, num_rows: Optional[int] = None, 
                     last_analyzed: Optional[str] = None) -> None:
        """Insert or update table record."""
        with self._get_connection() as conn:
            conn.execute("""
                INSERT OR REPLACE INTO tables 
                (owner, table_name, num_rows, last_analyzed, last_updated)
                VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
            """, (owner, table_name, num_rows, last_analyzed))
            conn.commit()
    
    def upsert_view(self, owner: str, view_name: str, text: Optional[str] = None) -> None:
        """Insert or update view record."""
        with self._get_connection() as conn:
            conn.execute("""
                INSERT OR REPLACE INTO views 
                (owner, view_name, text, last_updated)
                VALUES (?, ?, ?, CURRENT_TIMESTAMP)
            """, (owner, view_name, text))
            conn.commit()
    
    def upsert_column(self, owner: str, table_name: str, column_name: str,
                      data_type: Optional[str] = None, data_length: Optional[int] = None,
                      data_precision: Optional[int] = None, data_scale: Optional[int] = None,
                      nullable: Optional[str] = None, data_default: Optional[str] = None,
                      is_pii: bool = False) -> None:
        """Insert or update column record."""
        with self._get_connection() as conn:
            conn.execute("""
                INSERT OR REPLACE INTO columns 
                (owner, table_name, column_name, data_type, data_length, data_precision,
                 data_scale, nullable, data_default, is_pii, last_updated)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            """, (owner, table_name, column_name, data_type, data_length, 
                  data_precision, data_scale, nullable, data_default, is_pii))
            conn.commit()
    
    def upsert_table_comment(self, owner: str, table_name: str, comments: Optional[str]) -> None:
        """Insert or update table comment."""
        if comments:
            with self._get_connection() as conn:
                conn.execute("""
                    INSERT OR REPLACE INTO table_comments 
                    (owner, table_name, comments, last_updated)
                    VALUES (?, ?, ?, CURRENT_TIMESTAMP)
                """, (owner, table_name, comments))
                conn.commit()
    
    def upsert_column_comment(self, owner: str, table_name: str, column_name: str, 
                             comments: Optional[str]) -> None:
        """Insert or update column comment."""
        if comments:
            with self._get_connection() as conn:
                conn.execute("""
                    INSERT OR REPLACE INTO column_comments 
                    (owner, table_name, column_name, comments, last_updated)
                    VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
                """, (owner, table_name, column_name, comments))
                conn.commit()
    
    def upsert_constraint(self, owner: str, table_name: str, constraint_name: str,
                         constraint_type: str, r_owner: Optional[str] = None,
                         r_table: Optional[str] = None, r_constraint: Optional[str] = None) -> None:
        """Insert or update constraint record."""
        with self._get_connection() as conn:
            conn.execute("""
                INSERT OR REPLACE INTO constraints 
                (owner, table_name, constraint_name, constraint_type, r_owner, r_table, 
                 r_constraint, last_updated)
                VALUES (?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            """, (owner, table_name, constraint_name, constraint_type, 
                  r_owner, r_table, r_constraint))
            conn.commit()
    
    def upsert_constraint_column(self, owner: str, constraint_name: str, table_name: str,
                               column_name: str, position: int) -> None:
        """Insert or update constraint column record."""
        with self._get_connection() as conn:
            conn.execute("""
                INSERT OR REPLACE INTO cons_columns 
                (owner, constraint_name, table_name, column_name, position, last_updated)
                VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            """, (owner, constraint_name, table_name, column_name, position))
            conn.commit()
    
    def upsert_relationship(self, fk_owner: str, fk_table: str, fk_constraint: str,
                           pk_owner: str, pk_table: str, pk_constraint: str,
                           edge_type: str = "FK_TO_PK", cardinality: Optional[str] = None,
                           colmap: Optional[Dict] = None, quality: Optional[float] = None) -> None:
        """Insert or update relationship record."""
        colmap_json = json.dumps(colmap) if colmap else None
        with self._get_connection() as conn:
            conn.execute("""
                INSERT OR REPLACE INTO relationships 
                (fk_owner, fk_table, fk_constraint, pk_owner, pk_table, pk_constraint,
                 edge_type, cardinality, colmap_json, quality, last_updated)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            """, (fk_owner, fk_table, fk_constraint, pk_owner, pk_table, pk_constraint,
                  edge_type, cardinality, colmap_json, quality))
            conn.commit()
    
    def upsert_dependency(self, owner: str, name: str, type_: str,
                         ref_owner: str, ref_name: str, ref_type: str) -> None:
        """Insert or update dependency record."""
        with self._get_connection() as conn:
            conn.execute("""
                INSERT OR REPLACE INTO dependencies 
                (owner, name, type, ref_owner, ref_name, ref_type, last_updated)
                VALUES (?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            """, (owner, name, type_, ref_owner, ref_name, ref_type))
            conn.commit()
    
    def upsert_embedding(self, entity_type: str, owner: str, name: str,
                        extra: Optional[str], vector: bytes) -> None:
        """Insert or update embedding record."""
        with self._get_connection() as conn:
            conn.execute("""
                INSERT OR REPLACE INTO catalog_embeddings 
                (entity_type, owner, name, extra, vector, last_updated)
                VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            """, (entity_type, owner, name, extra, vector))
            conn.commit()
    
    def get_tables_for_owner(self, owner: str) -> List[Dict[str, Any]]:
        """Get all tables for a specific owner."""
        with self._get_connection() as conn:
            cursor = conn.execute("""
                SELECT * FROM tables WHERE owner = ? ORDER BY table_name
            """, (owner,))
            return [dict(row) for row in cursor.fetchall()]
    
    def get_relationships(self) -> List[Dict[str, Any]]:
        """Get all relationships for graph building."""
        with self._get_connection() as conn:
            cursor = conn.execute("""
                SELECT * FROM relationships ORDER BY fk_owner, fk_table, pk_owner, pk_table
            """)
            return [dict(row) for row in cursor.fetchall()]
    
    def get_catalog_entities_for_search(self) -> List[Dict[str, Any]]:
        """Get all catalog entities for search indexing."""
        entities = []
        
        with self._get_connection() as conn:
            # Tables with comments
            cursor = conn.execute("""
                SELECT t.owner, t.table_name, tc.comments, 'table' as entity_type
                FROM tables t
                LEFT JOIN table_comments tc ON t.owner = tc.owner AND t.table_name = tc.table_name
                ORDER BY t.owner, t.table_name
            """)
            entities.extend([dict(row) for row in cursor.fetchall()])
            
            # Columns with comments
            cursor = conn.execute("""
                SELECT c.owner, c.table_name, c.column_name, c.data_type, 
                       cc.comments, 'column' as entity_type
                FROM columns c
                LEFT JOIN column_comments cc ON c.owner = cc.owner 
                    AND c.table_name = cc.table_name 
                    AND c.column_name = cc.column_name
                ORDER BY c.owner, c.table_name, c.column_name
            """)
            entities.extend([dict(row) for row in cursor.fetchall()])
            
            # Views
            cursor = conn.execute("""
                SELECT owner, view_name, 'view' as entity_type
                FROM views
                ORDER BY owner, view_name
            """)
            entities.extend([dict(row) for row in cursor.fetchall()])
        
        return entities
    
    def health_check(self) -> Dict[str, Any]:
        """Perform health check on catalog database."""
        try:
            with self._get_connection() as conn:
                cursor = conn.execute("SELECT COUNT(*) as count FROM sqlite_master WHERE type='table'")
                table_count = cursor.fetchone()['count']
                
                cursor = conn.execute("SELECT COUNT(*) as count FROM tables")
                tables_count = cursor.fetchone()['count']
                
                cursor = conn.execute("SELECT COUNT(*) as count FROM relationships")
                relationships_count = cursor.fetchone()['count']
                
                return {
                    "status": "healthy",
                    "database_tables": table_count,
                    "catalog_tables": tables_count,
                    "relationships": relationships_count,
                    "timestamp": datetime.utcnow().isoformat()
                }
        except Exception as e:
            return {
                "status": "unhealthy",
                "error": str(e),
                "timestamp": datetime.utcnow().isoformat()
            }