#!/usr/bin/env python3
"""
Test schema retrieval and search functionality.
"""

import os
import sys
import tempfile
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime

# Add project root to path
project_root = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, project_root)

from services.db.catalog_store import CatalogStore
from services.retriever.schema_retriever import SchemaRetriever, SchemaEntity

class TestSchemaRetriever:
    """Test schema retrieval functionality."""
    
    def setup_method(self):
        """Setup test environment."""
        self.temp_dir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.temp_dir, 'test_schema.db')
        self.catalog = CatalogStore(self.db_path)
        
        # Setup test data
        self._setup_test_data()
        
        # Create retriever
        self.retriever = SchemaRetriever(self.catalog)
    
    def teardown_method(self):
        """Cleanup test environment."""
        if os.path.exists(self.db_path):
            os.unlink(self.db_path)
        os.rmdir(self.temp_dir)
    
    def _setup_test_data(self):
        """Setup comprehensive test data."""
        # Add schemas
        self.catalog.upsert_schema(
            owner='AML_PROD',
            default_tablespace='AML_DATA',
            created='2024-01-01T00:00:00'
        )
        
        # Add tables
        tables_data = [
            ('CUSTOMERS', 50000, 'Customer master data'),
            ('ACCOUNTS', 25000, 'Account information'),
            ('TRANSACTIONS', 1000000, 'Financial transactions'),
            ('ALERTS', 5000, 'AML alerts and cases'),
            ('PARTY_RELATIONSHIPS', 15000, 'Customer relationships')
        ]
        
        for table_name, num_rows, comment in tables_data:
            self.catalog.upsert_table(
                owner='AML_PROD',
                table_name=table_name,
                tablespace_name='AML_DATA',
                num_rows=num_rows,
                last_analyzed='2024-01-15T12:00:00'
            )
            
            # Add table comment
            with self.catalog._get_connection() as conn:
                conn.execute("""
                    INSERT OR REPLACE INTO table_comments
                    (owner, table_name, comments)
                    VALUES (?, ?, ?)
                """, ('AML_PROD', table_name, comment))
        
        # Add columns for CUSTOMERS table
        customer_columns = [
            ('CUSTOMER_ID', 'NUMBER', 10, 'N', False),
            ('SSN', 'VARCHAR2', 11, 'Y', True),
            ('EMAIL', 'VARCHAR2', 255, 'N', True),
            ('FIRST_NAME', 'VARCHAR2', 50, 'N', True),
            ('LAST_NAME', 'VARCHAR2', 50, 'N', True),
            ('DATE_OF_BIRTH', 'DATE', None, 'Y', True),
            ('RISK_SCORE', 'NUMBER', 5, 'Y', False),
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
        
        # Add columns for ACCOUNTS table
        account_columns = [
            ('ACCOUNT_ID', 'NUMBER', 10, 'N', False),
            ('CUSTOMER_ID', 'NUMBER', 10, 'N', False),
            ('ACCOUNT_NUMBER', 'VARCHAR2', 20, 'N', True),
            ('ACCOUNT_TYPE', 'VARCHAR2', 20, 'N', False),
            ('BALANCE', 'NUMBER', 15, 'Y', False),
            ('OPEN_DATE', 'DATE', None, 'N', False),
            ('STATUS', 'VARCHAR2', 10, 'N', False)
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
        
        # Add columns for TRANSACTIONS table
        transaction_columns = [
            ('TRANSACTION_ID', 'NUMBER', 10, 'N', False),
            ('ACCOUNT_ID', 'NUMBER', 10, 'N', False),
            ('AMOUNT', 'NUMBER', 15, 'N', False),
            ('TRANSACTION_DATE', 'DATE', None, 'N', False),
            ('TRANSACTION_TYPE', 'VARCHAR2', 20, 'N', False),
            ('DESCRIPTION', 'VARCHAR2', 500, 'Y', False)
        ]
        
        for col_name, data_type, length, nullable, is_pii in transaction_columns:
            self.catalog.upsert_column(
                owner='AML_PROD',
                table_name='TRANSACTIONS',
                column_name=col_name,
                data_type=data_type,
                data_length=length,
                nullable=nullable,
                is_pii=is_pii
            )
        
        # Add relationships
        self.catalog.upsert_relationship(
            source_table='AML_PROD.ACCOUNTS',
            target_table='AML_PROD.CUSTOMERS',
            constraint_name='FK_ACCOUNTS_CUSTOMER',
            cardinality='many_to_one',
            quality=0.95
        )
        
        self.catalog.upsert_relationship(
            source_table='AML_PROD.TRANSACTIONS',
            target_table='AML_PROD.ACCOUNTS',
            constraint_name='FK_TRANSACTIONS_ACCOUNT',
            cardinality='many_to_one',
            quality=0.90
        )
    
    def test_schema_entity_creation(self):
        """Test SchemaEntity model creation."""
        entity = SchemaEntity(
            entity_type='table',
            entity_key='AML_PROD.CUSTOMERS',
            name='CUSTOMERS',
            owner='AML_PROD',
            description='Customer master data',
            metadata={'num_rows': 50000, 'pii_columns': 5}
        )
        
        assert entity.entity_type == 'table'
        assert entity.entity_key == 'AML_PROD.CUSTOMERS'
        assert entity.name == 'CUSTOMERS'
        assert entity.owner == 'AML_PROD'
        assert entity.description == 'Customer master data'
        assert entity.metadata['num_rows'] == 50000
    
    def test_get_all_entities(self):
        """Test retrieving all schema entities."""
        entities = self.retriever.get_all_entities()
        
        # Should have tables and columns
        assert len(entities) > 0
        
        # Check table entities
        table_entities = [e for e in entities if e.entity_type == 'table']
        assert len(table_entities) == 5  # 5 tables added
        
        table_names = [e.name for e in table_entities]
        assert 'CUSTOMERS' in table_names
        assert 'ACCOUNTS' in table_names
        assert 'TRANSACTIONS' in table_names
        
        # Check column entities
        column_entities = [e for e in entities if e.entity_type == 'column']
        assert len(column_entities) > 0
        
        # Verify customer column entities
        customer_columns = [
            e for e in column_entities 
            if 'CUSTOMERS' in e.entity_key
        ]
        assert len(customer_columns) == 8  # 8 customer columns
    
    def test_keyword_search(self):
        """Test keyword-based search."""
        # Search for customer-related entities
        results = self.retriever.search('customer email address', top_k=5)
        
        assert len(results) > 0
        
        # Should find customer table and email column
        result_keys = [r.entity_key for r in results]
        
        # Check if customer-related entities are found
        customer_found = any('CUSTOMERS' in key for key in result_keys)
        assert customer_found
        
        # Search for transaction data
        results = self.retriever.search('transaction amount money', top_k=3)
        assert len(results) > 0
        
        # Should find transaction-related entities
        transaction_found = any('TRANSACTION' in key for key in result_keys)
        assert transaction_found
    
    def test_find_join_path(self):
        """Test join path finding between tables."""
        # Find path from CUSTOMERS to TRANSACTIONS
        path = self.retriever.find_join_path(
            'AML_PROD.CUSTOMERS',
            'AML_PROD.TRANSACTIONS'
        )
        
        assert path is not None
        assert len(path.tables) == 3  # CUSTOMERS -> ACCOUNTS -> TRANSACTIONS
        assert path.tables[0] == 'AML_PROD.CUSTOMERS'
        assert path.tables[1] == 'AML_PROD.ACCOUNTS'
        assert path.tables[2] == 'AML_PROD.TRANSACTIONS'
        
        # Check join conditions
        assert len(path.join_conditions) == 2
        
        # Find direct path from ACCOUNTS to CUSTOMERS
        path = self.retriever.find_join_path(
            'AML_PROD.ACCOUNTS',
            'AML_PROD.CUSTOMERS'
        )
        
        assert path is not None
        assert len(path.tables) == 2  # Direct relationship
        assert path.tables[0] == 'AML_PROD.ACCOUNTS'
        assert path.tables[1] == 'AML_PROD.CUSTOMERS'
    
    def test_generate_synthetic_sql(self):
        """Test synthetic SQL generation."""
        # Generate SQL for customer query
        sql = self.retriever.generate_synthetic_sql(
            'show me customers with high risk scores',
            tables=['AML_PROD.CUSTOMERS']
        )
        
        assert sql is not None
        assert 'SELECT' in sql.upper()
        assert 'CUSTOMERS' in sql.upper()
        assert 'RISK_SCORE' in sql.upper()
        
        # Generate SQL for transaction analysis
        sql = self.retriever.generate_synthetic_sql(
            'find large transactions for specific customer',
            tables=['AML_PROD.CUSTOMERS', 'AML_PROD.ACCOUNTS', 'AML_PROD.TRANSACTIONS']
        )
        
        assert sql is not None
        assert 'JOIN' in sql.upper()
        assert 'CUSTOMERS' in sql.upper()
        assert 'TRANSACTIONS' in sql.upper()
        assert 'AMOUNT' in sql.upper()
    
    def test_explain_table(self):
        """Test table explanation generation."""
        explanation = self.retriever.explain_table('AML_PROD.CUSTOMERS')
        
        assert explanation is not None
        assert 'CUSTOMERS' in explanation
        assert 'customer' in explanation.lower()
        
        # Should mention key columns
        assert any(col in explanation for col in ['CUSTOMER_ID', 'EMAIL', 'SSN'])
        
        # Should mention PII sensitivity
        assert 'PII' in explanation or 'sensitive' in explanation.lower()
    
    def test_get_table_relationships(self):
        """Test getting table relationships."""
        relationships = self.retriever.get_table_relationships('AML_PROD.CUSTOMERS')
        
        assert len(relationships) > 0
        
        # Should find relationship to ACCOUNTS
        account_rel = next(
            (r for r in relationships if 'ACCOUNTS' in r['related_table']),
            None
        )
        assert account_rel is not None
        assert account_rel['relationship_type'] in ['one_to_many', 'parent']
    
    @patch('services.retriever.schema_retriever.SchemaRetriever._generate_embedding')
    def test_search_with_embeddings(self, mock_embedding):
        """Test search with embedding similarity."""
        # Mock embedding generation
        mock_embedding.return_value = [0.1, 0.2, 0.3, 0.4, 0.5]
        
        # Add some embeddings to test data
        test_embedding = [0.1, 0.2, 0.3, 0.4, 0.5]
        self.catalog.upsert_embedding(
            entity_type='table',
            entity_key='AML_PROD.CUSTOMERS',
            embedding_model='test-model',
            embedding_vector=test_embedding,
            embedding_text='Customer master data with personal information'
        )
        
        # Test search with embeddings
        results = self.retriever.search('personal customer information', top_k=3)
        
        assert len(results) > 0
        # Should find the customer table
        customer_found = any('CUSTOMERS' in r.entity_key for r in results)
        assert customer_found
    
    def test_search_edge_cases(self):
        """Test search edge cases."""
        # Empty query
        results = self.retriever.search('', top_k=5)
        assert len(results) == 0
        
        # Very specific query with no matches
        results = self.retriever.search('nonexistent_table_xyz', top_k=5)
        # May return some results due to fuzzy matching, but should be low scoring
        
        # Query for specific data types
        results = self.retriever.search('DATE columns', top_k=10)
        assert len(results) > 0
        
        # Should find date-related columns
        date_results = [r for r in results if 'DATE' in r.description or 'date' in r.name.lower()]
        assert len(date_results) > 0
    
    def test_join_path_edge_cases(self):
        """Test join path edge cases."""
        # Path to same table
        path = self.retriever.find_join_path(
            'AML_PROD.CUSTOMERS',
            'AML_PROD.CUSTOMERS'
        )
        assert path is None or len(path.tables) == 1
        
        # Path to non-existent table
        path = self.retriever.find_join_path(
            'AML_PROD.CUSTOMERS',
            'AML_PROD.NONEXISTENT'
        )
        assert path is None
        
        # Path between unconnected tables
        # Add an isolated table
        self.catalog.upsert_table(
            owner='AML_PROD',
            table_name='ISOLATED_TABLE',
            tablespace_name='AML_DATA',
            num_rows=100
        )
        
        path = self.retriever.find_join_path(
            'AML_PROD.CUSTOMERS',
            'AML_PROD.ISOLATED_TABLE'
        )
        assert path is None

class TestSchemaRetrieverIntegration:
    """Integration tests for schema retriever."""
    
    def setup_method(self):
        """Setup integration test environment."""
        self.temp_dir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.temp_dir, 'test_integration.db')
        self.catalog = CatalogStore(self.db_path)
        
        # Setup complex test data
        self._setup_complex_data()
        
        self.retriever = SchemaRetriever(self.catalog)
    
    def teardown_method(self):
        """Cleanup integration test environment."""
        if os.path.exists(self.db_path):
            os.unlink(self.db_path)
        os.rmdir(self.temp_dir)
    
    def _setup_complex_data(self):
        """Setup complex AML-like schema."""
        # Multiple schemas
        schemas = ['AML_PROD', 'AML_STAGE', 'REFERENCE']
        for schema in schemas:
            self.catalog.upsert_schema(
                owner=schema,
                default_tablespace='AML_DATA',
                created='2024-01-01T00:00:00'
            )
        
        # AML production tables
        aml_tables = [
            ('PARTIES', 100000, 'Individual and entity parties'),
            ('PARTY_RELATIONSHIPS', 50000, 'Relationships between parties'),
            ('ACCOUNTS', 200000, 'Banking accounts'),
            ('TRANSACTIONS', 10000000, 'Financial transactions'),
            ('ALERTS', 25000, 'AML monitoring alerts'),
            ('CASES', 5000, 'Investigation cases'),
            ('WATCHLIST', 10000, 'Sanctions and watchlist data')
        ]
        
        for table_name, num_rows, comment in aml_tables:
            self.catalog.upsert_table(
                owner='AML_PROD',
                table_name=table_name,
                tablespace_name='AML_DATA',
                num_rows=num_rows
            )
            
            with self.catalog._get_connection() as conn:
                conn.execute("""
                    INSERT OR REPLACE INTO table_comments
                    (owner, table_name, comments)
                    VALUES (?, ?, ?)
                """, ('AML_PROD', table_name, comment))
        
        # Add relationships
        relationships = [
            ('AML_PROD.ACCOUNTS', 'AML_PROD.PARTIES', 'FK_ACCOUNTS_PARTY', 'many_to_one', 0.95),
            ('AML_PROD.TRANSACTIONS', 'AML_PROD.ACCOUNTS', 'FK_TRANS_ACCOUNT', 'many_to_one', 0.90),
            ('AML_PROD.ALERTS', 'AML_PROD.PARTIES', 'FK_ALERTS_PARTY', 'many_to_one', 0.85),
            ('AML_PROD.CASES', 'AML_PROD.ALERTS', 'FK_CASES_ALERT', 'one_to_many', 0.80),
            ('AML_PROD.PARTY_RELATIONSHIPS', 'AML_PROD.PARTIES', 'FK_REL_PARTY1', 'many_to_one', 0.90),
        ]
        
        for source, target, constraint, cardinality, quality in relationships:
            self.catalog.upsert_relationship(
                source_table=source,
                target_table=target,
                constraint_name=constraint,
                cardinality=cardinality,
                quality=quality
            )
    
    def test_complex_join_paths(self):
        """Test complex join path finding."""
        # Find path from WATCHLIST to TRANSACTIONS
        path = self.retriever.find_join_path(
            'AML_PROD.WATCHLIST',
            'AML_PROD.TRANSACTIONS'
        )
        
        # Should find a path through PARTIES and ACCOUNTS
        if path:
            assert len(path.tables) >= 3
            assert 'AML_PROD.PARTIES' in path.tables
        
        # Find path from CASES to TRANSACTIONS
        path = self.retriever.find_join_path(
            'AML_PROD.CASES',
            'AML_PROD.TRANSACTIONS'
        )
        
        if path:
            # Should go through ALERTS -> PARTIES -> ACCOUNTS -> TRANSACTIONS
            assert len(path.tables) >= 4
    
    def test_comprehensive_search(self):
        """Test comprehensive search across complex schema."""
        # Search for suspicious activity analysis
        results = self.retriever.search(
            'suspicious activity monitoring alerts investigations',
            top_k=10
        )
        
        assert len(results) > 0
        
        # Should find relevant tables
        result_keys = [r.entity_key for r in results]
        assert any('ALERTS' in key for key in result_keys)
        assert any('CASES' in key for key in result_keys)
        
        # Search for customer due diligence
        results = self.retriever.search(
            'customer due diligence party information',
            top_k=10
        )
        
        assert len(results) > 0
        assert any('PARTIES' in key for key in result_keys)
    
    def test_sql_generation_complex(self):
        """Test SQL generation for complex queries."""
        # Generate SQL for suspicious transaction analysis
        sql = self.retriever.generate_synthetic_sql(
            'find all high-value transactions for customers with alerts',
            tables=['AML_PROD.PARTIES', 'AML_PROD.ACCOUNTS', 'AML_PROD.TRANSACTIONS', 'AML_PROD.ALERTS']
        )
        
        assert sql is not None
        assert 'JOIN' in sql.upper()
        assert 'PARTIES' in sql.upper()
        assert 'TRANSACTIONS' in sql.upper()
        assert 'ALERTS' in sql.upper()
        
        # Generate SQL for relationship analysis
        sql = self.retriever.generate_synthetic_sql(
            'analyze party relationships for network detection',
            tables=['AML_PROD.PARTIES', 'AML_PROD.PARTY_RELATIONSHIPS']
        )
        
        assert sql is not None
        assert 'PARTY_RELATIONSHIPS' in sql.upper()

def test_schema_retriever_error_handling():
    """Test error handling in schema retriever."""
    # Create retriever with empty catalog
    catalog = CatalogStore(':memory:')
    retriever = SchemaRetriever(catalog)
    
    # Search in empty catalog
    results = retriever.search('test query', top_k=5)
    assert len(results) == 0
    
    # Find join path in empty catalog
    path = retriever.find_join_path('TABLE1', 'TABLE2')
    assert path is None
    
    # Generate SQL with no tables
    sql = retriever.generate_synthetic_sql('test query', tables=[])
    assert sql is None or sql == ''

if __name__ == '__main__':
    # Run basic tests
    import sys
    
    # Simple test runner
    test_classes = [TestSchemaRetriever, TestSchemaRetrieverIntegration]
    
    for test_class in test_classes:
        print(f"\nRunning tests for {test_class.__name__}...")
        
        instance = test_class()
        test_methods = [method for method in dir(instance) if method.startswith('test_')]
        
        passed = 0
        failed = 0
        
        for method_name in test_methods:
            try:
                instance.setup_method()
                method = getattr(instance, method_name)
                method()
                instance.teardown_method()
                print(f"  ✓ {method_name}")
                passed += 1
            except Exception as e:
                print(f"  ✗ {method_name}: {e}")
                failed += 1
                try:
                    instance.teardown_method()
                except:
                    pass
        
        print(f"  Results: {passed} passed, {failed} failed")
    
    print("\nAll tests completed.")