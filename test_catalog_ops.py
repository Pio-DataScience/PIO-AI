#!/usr/bin/env python3
"""
Test catalog operations and SQLite storage.
"""

import os
import sys
import tempfile
import pytest
from unittest.mock import Mock, patch
from datetime import datetime

# Add project root to path
project_root = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, project_root)

from services.db.catalog_store import CatalogStore

class TestCatalogStore:
    """Test SQLite catalog operations."""
    
    def setup_method(self):
        """Setup test database."""
        self.temp_dir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.temp_dir, 'test_catalog.db')
        self.catalog = CatalogStore(self.db_path)
    
    def teardown_method(self):
        """Cleanup test database."""
        if os.path.exists(self.db_path):
            os.unlink(self.db_path)
        os.rmdir(self.temp_dir)
    
    def test_initialization(self):
        """Test database initialization."""
        # Check database file created
        assert os.path.exists(self.db_path)
        
        # Check tables created
        with self.catalog._get_connection() as conn:
            cursor = conn.execute("""
                SELECT name FROM sqlite_master
                WHERE type='table' AND name NOT LIKE 'sqlite_%'
                ORDER BY name
            """)
            tables = [row[0] for row in cursor.fetchall()]
            
            expected_tables = [
                'columns', 'constraints', 'dependencies', 'embeddings',
                'relationships', 'schemas', 'table_comments', 'tables', 'views'
            ]
            assert sorted(tables) == sorted(expected_tables)
    
    def test_upsert_schema(self):
        """Test schema upsert operations."""
        # Insert schema
        self.catalog.upsert_schema(
            owner='TEST_SCHEMA',
            default_tablespace='USERS',
            created=datetime.utcnow().isoformat()
        )
        
        # Verify insert
        with self.catalog._get_connection() as conn:
            cursor = conn.execute(
                "SELECT owner, default_tablespace FROM schemas WHERE owner = ?",
                ('TEST_SCHEMA',)
            )
            row = cursor.fetchone()
            assert row is not None
            assert row['owner'] == 'TEST_SCHEMA'
            assert row['default_tablespace'] == 'USERS'
        
        # Update schema
        self.catalog.upsert_schema(
            owner='TEST_SCHEMA',
            default_tablespace='SYSTEM',
            created=datetime.utcnow().isoformat()
        )
        
        # Verify update
        with self.catalog._get_connection() as conn:
            cursor = conn.execute(
                "SELECT default_tablespace FROM schemas WHERE owner = ?",
                ('TEST_SCHEMA',)
            )
            row = cursor.fetchone()
            assert row['default_tablespace'] == 'SYSTEM'
    
    def test_upsert_table(self):
        """Test table upsert operations."""
        # Insert schema first
        self.catalog.upsert_schema(
            owner='TEST_SCHEMA',
            default_tablespace='USERS',
            created=datetime.utcnow().isoformat()
        )
        
        # Insert table
        self.catalog.upsert_table(
            owner='TEST_SCHEMA',
            table_name='TEST_TABLE',
            tablespace_name='USERS',
            num_rows=1000,
            last_analyzed=datetime.utcnow().isoformat()
        )
        
        # Verify insert
        with self.catalog._get_connection() as conn:
            cursor = conn.execute("""
                SELECT owner, table_name, num_rows
                FROM tables WHERE owner = ? AND table_name = ?
            """, ('TEST_SCHEMA', 'TEST_TABLE'))
            row = cursor.fetchone()
            assert row is not None
            assert row['num_rows'] == 1000
    
    def test_upsert_column(self):
        """Test column upsert operations."""
        # Setup prerequisites
        self.catalog.upsert_schema(
            owner='TEST_SCHEMA',
            default_tablespace='USERS',
            created=datetime.utcnow().isoformat()
        )
        self.catalog.upsert_table(
            owner='TEST_SCHEMA',
            table_name='TEST_TABLE',
            tablespace_name='USERS',
            num_rows=100
        )
        
        # Insert column
        self.catalog.upsert_column(
            owner='TEST_SCHEMA',
            table_name='TEST_TABLE',
            column_name='ID',
            data_type='NUMBER',
            data_length=10,
            nullable='N',
            is_pii=False
        )
        
        # Verify insert
        with self.catalog._get_connection() as conn:
            cursor = conn.execute("""
                SELECT column_name, data_type, nullable, is_pii
                FROM columns
                WHERE owner = ? AND table_name = ? AND column_name = ?
            """, ('TEST_SCHEMA', 'TEST_TABLE', 'ID'))
            row = cursor.fetchone()
            assert row is not None
            assert row['data_type'] == 'NUMBER'
            assert row['nullable'] == 'N'
            assert row['is_pii'] == 0  # SQLite stores as int
    
    def test_upsert_constraint(self):
        """Test constraint upsert operations."""
        # Setup prerequisites
        self.catalog.upsert_schema(
            owner='TEST_SCHEMA',
            default_tablespace='USERS',
            created=datetime.utcnow().isoformat()
        )
        self.catalog.upsert_table(
            owner='TEST_SCHEMA',
            table_name='TEST_TABLE',
            tablespace_name='USERS',
            num_rows=100
        )
        
        # Insert constraint
        self.catalog.upsert_constraint(
            owner='TEST_SCHEMA',
            constraint_name='PK_TEST',
            constraint_type='P',
            table_name='TEST_TABLE',
            r_owner='TEST_SCHEMA',
            r_constraint_name='PK_REF'
        )
        
        # Verify insert
        with self.catalog._get_connection() as conn:
            cursor = conn.execute("""
                SELECT constraint_name, constraint_type, table_name
                FROM constraints
                WHERE owner = ? AND constraint_name = ?
            """, ('TEST_SCHEMA', 'PK_TEST'))
            row = cursor.fetchone()
            assert row is not None
            assert row['constraint_type'] == 'P'
            assert row['table_name'] == 'TEST_TABLE'
    
    def test_upsert_relationship(self):
        """Test relationship upsert operations."""
        # Insert relationship
        self.catalog.upsert_relationship(
            source_table='SCHEMA1.TABLE1',
            target_table='SCHEMA2.TABLE2',
            constraint_name='FK_TEST',
            cardinality='many_to_one',
            quality=0.85
        )
        
        # Verify insert
        with self.catalog._get_connection() as conn:
            cursor = conn.execute("""
                SELECT source_table, target_table, cardinality, quality
                FROM relationships
                WHERE constraint_name = ?
            """, ('FK_TEST',))
            row = cursor.fetchone()
            assert row is not None
            assert row['source_table'] == 'SCHEMA1.TABLE1'
            assert row['target_table'] == 'SCHEMA2.TABLE2'
            assert row['cardinality'] == 'many_to_one'
            assert abs(row['quality'] - 0.85) < 0.001
    
    def test_upsert_embedding(self):
        """Test embedding upsert operations."""
        # Insert embedding
        test_embedding = [0.1, 0.2, 0.3, 0.4, 0.5]
        
        self.catalog.upsert_embedding(
            entity_type='table',
            entity_key='SCHEMA.TABLE',
            embedding_model='test-model',
            embedding_vector=test_embedding,
            embedding_text='Test table for embeddings'
        )
        
        # Verify insert
        with self.catalog._get_connection() as conn:
            cursor = conn.execute("""
                SELECT entity_type, entity_key, embedding_model, embedding_text
                FROM embeddings
                WHERE entity_key = ?
            """, ('SCHEMA.TABLE',))
            row = cursor.fetchone()
            assert row is not None
            assert row['entity_type'] == 'table'
            assert row['embedding_model'] == 'test-model'
            assert row['embedding_text'] == 'Test table for embeddings'
    
    def test_health_check(self):
        """Test catalog health check."""
        # Empty catalog
        health = self.catalog.health_check()
        assert health['status'] == 'healthy'
        assert health['catalog_tables'] == 0
        assert health['relationships'] == 0
        assert health['embeddings'] == 0
        
        # Add some data
        self.catalog.upsert_schema(
            owner='TEST',
            default_tablespace='USERS',
            created=datetime.utcnow().isoformat()
        )
        self.catalog.upsert_table(
            owner='TEST',
            table_name='TABLE1',
            tablespace_name='USERS',
            num_rows=100
        )
        self.catalog.upsert_relationship(
            source_table='TEST.TABLE1',
            target_table='TEST.TABLE2',
            constraint_name='FK_TEST',
            cardinality='many_to_one',
            quality=0.9
        )
        
        health = self.catalog.health_check()
        assert health['status'] == 'healthy'
        assert health['catalog_tables'] == 1
        assert health['relationships'] == 1
    
    def test_get_all_tables(self):
        """Test retrieving all tables."""
        # Add test data
        self.catalog.upsert_schema(
            owner='SCHEMA1',
            default_tablespace='USERS',
            created=datetime.utcnow().isoformat()
        )
        self.catalog.upsert_schema(
            owner='SCHEMA2',
            default_tablespace='USERS',
            created=datetime.utcnow().isoformat()
        )
        
        for i in range(3):
            self.catalog.upsert_table(
                owner='SCHEMA1',
                table_name=f'TABLE{i+1}',
                tablespace_name='USERS',
                num_rows=100 * (i + 1)
            )
        
        # Get all tables
        tables = self.catalog.get_all_tables()
        assert len(tables) == 3
        
        table_names = [t['table_name'] for t in tables]
        assert 'TABLE1' in table_names
        assert 'TABLE2' in table_names
        assert 'TABLE3' in table_names
    
    def test_get_table_columns(self):
        """Test retrieving table columns."""
        # Setup table
        self.catalog.upsert_schema(
            owner='TEST',
            default_tablespace='USERS',
            created=datetime.utcnow().isoformat()
        )
        self.catalog.upsert_table(
            owner='TEST',
            table_name='USERS',
            tablespace_name='USERS',
            num_rows=1000
        )
        
        # Add columns
        columns_data = [
            ('ID', 'NUMBER', 10, 'N', False),
            ('EMAIL', 'VARCHAR2', 255, 'N', True),
            ('NAME', 'VARCHAR2', 100, 'Y', False)
        ]
        
        for col_name, data_type, length, nullable, is_pii in columns_data:
            self.catalog.upsert_column(
                owner='TEST',
                table_name='USERS',
                column_name=col_name,
                data_type=data_type,
                data_length=length,
                nullable=nullable,
                is_pii=is_pii
            )
        
        # Get columns
        columns = self.catalog.get_table_columns('TEST', 'USERS')
        assert len(columns) == 3
        
        # Check PII detection
        email_col = next(c for c in columns if c['column_name'] == 'EMAIL')
        assert email_col['is_pii'] == 1  # SQLite stores as int
        
        id_col = next(c for c in columns if c['column_name'] == 'ID')
        assert id_col['is_pii'] == 0

class TestCatalogIntegration:
    """Integration tests for catalog operations."""
    
    def setup_method(self):
        """Setup test database."""
        self.temp_dir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.temp_dir, 'test_integration.db')
        self.catalog = CatalogStore(self.db_path)
    
    def teardown_method(self):
        """Cleanup test database."""
        if os.path.exists(self.db_path):
            os.unlink(self.db_path)
        os.rmdir(self.temp_dir)
    
    def test_full_catalog_workflow(self):
        """Test complete catalog workflow."""
        # 1. Add schema
        self.catalog.upsert_schema(
            owner='AML_PROD',
            default_tablespace='AML_DATA',
            created='2024-01-01T00:00:00'
        )
        
        # 2. Add tables
        tables = [
            ('CUSTOMERS', 50000),
            ('ACCOUNTS', 25000),
            ('TRANSACTIONS', 1000000)
        ]
        
        for table_name, num_rows in tables:
            self.catalog.upsert_table(
                owner='AML_PROD',
                table_name=table_name,
                tablespace_name='AML_DATA',
                num_rows=num_rows,
                last_analyzed='2024-01-15T12:00:00'
            )
        
        # 3. Add columns for CUSTOMERS
        customer_columns = [
            ('CUSTOMER_ID', 'NUMBER', 10, 'N', False),
            ('SSN', 'VARCHAR2', 11, 'Y', True),
            ('EMAIL', 'VARCHAR2', 255, 'N', True),
            ('FIRST_NAME', 'VARCHAR2', 50, 'N', True),
            ('LAST_NAME', 'VARCHAR2', 50, 'N', True),
            ('PHONE', 'VARCHAR2', 20, 'Y', True),
            ('STATUS', 'VARCHAR2', 10, 'N', False)
        ]
        
        for col_name, data_type, length, nullable, is_pii in customer_columns:
            self.catalog.upsert_column(
                owner='AML_PROD',
                table_name='CUSTOMERS',
                column_name=col_name,
                data_type=data_type,
                data_length=length,
                nullable=nullable,
                is_pii=is_pii
            )
        
        # 4. Add columns for ACCOUNTS
        account_columns = [
            ('ACCOUNT_ID', 'NUMBER', 10, 'N', False),
            ('CUSTOMER_ID', 'NUMBER', 10, 'N', False),
            ('ACCOUNT_NUMBER', 'VARCHAR2', 20, 'N', True),
            ('BALANCE', 'NUMBER', 15, 'Y', False)
        ]
        
        for col_name, data_type, length, nullable, is_pii in account_columns:
            self.catalog.upsert_column(
                owner='AML_PROD',
                table_name='ACCOUNTS',
                column_name=col_name,
                data_type=data_type,
                data_length=length,
                nullable=nullable,
                is_pii=is_pii
            )
        
        # 5. Add constraints
        self.catalog.upsert_constraint(
            owner='AML_PROD',
            constraint_name='PK_CUSTOMERS',
            constraint_type='P',
            table_name='CUSTOMERS'
        )
        
        self.catalog.upsert_constraint(
            owner='AML_PROD',
            constraint_name='FK_ACCOUNTS_CUSTOMER',
            constraint_type='R',
            table_name='ACCOUNTS',
            r_owner='AML_PROD',
            r_constraint_name='PK_CUSTOMERS'
        )
        
        # 6. Add relationships
        self.catalog.upsert_relationship(
            source_table='AML_PROD.ACCOUNTS',
            target_table='AML_PROD.CUSTOMERS',
            constraint_name='FK_ACCOUNTS_CUSTOMER',
            cardinality='many_to_one',
            quality=0.95
        )
        
        # 7. Verify complete workflow
        health = self.catalog.health_check()
        assert health['status'] == 'healthy'
        assert health['catalog_tables'] == 3
        assert health['relationships'] == 1
        
        # Get all tables
        all_tables = self.catalog.get_all_tables()
        assert len(all_tables) == 3
        
        # Check customer columns
        customer_cols = self.catalog.get_table_columns('AML_PROD', 'CUSTOMERS')
        assert len(customer_cols) == 7
        
        # Verify PII detection
        pii_columns = [c for c in customer_cols if c['is_pii']]
        assert len(pii_columns) == 4  # SSN, EMAIL, FIRST_NAME, LAST_NAME, PHONE
        
        # Check account columns
        account_cols = self.catalog.get_table_columns('AML_PROD', 'ACCOUNTS')
        assert len(account_cols) == 4
        
        # Verify account number is PII
        account_number_col = next(c for c in account_cols if c['column_name'] == 'ACCOUNT_NUMBER')
        assert account_number_col['is_pii'] == 1

def test_catalog_error_handling():
    """Test catalog error handling."""
    catalog = CatalogStore(':memory:')  # In-memory database
    
    # Test constraint violation (should handle gracefully)
    try:
        # Try to insert column without table
        catalog.upsert_column(
            owner='NONEXISTENT',
            table_name='NONEXISTENT',
            column_name='ID',
            data_type='NUMBER',
            nullable='N',
            is_pii=False
        )
        # Should not raise exception due to foreign key handling
    except Exception as e:
        pytest.fail(f"Unexpected exception: {e}")

if __name__ == '__main__':
    # Run tests
    pytest.main([__file__, '-v'])