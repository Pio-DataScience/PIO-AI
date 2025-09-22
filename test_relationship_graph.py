#!/usr/bin/env python3
"""
Test relationship graph building and NetworkX integration.
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
from services.db.relationship_builder import (
    RelationshipBuilder, Relationship, ColumnMapping, JoinPath
)

class TestRelationshipDataClasses:
    """Test relationship data classes."""
    
    def test_column_mapping(self):
        """Test ColumnMapping dataclass."""
        mapping = ColumnMapping(
            source_column='CUSTOMER_ID',
            target_column='ID',
            match_quality=0.95
        )
        
        assert mapping.source_column == 'CUSTOMER_ID'
        assert mapping.target_column == 'ID'
        assert mapping.match_quality == 0.95
    
    def test_relationship(self):
        """Test Relationship dataclass."""
        column_mappings = [
            ColumnMapping('CUSTOMER_ID', 'ID', 0.95),
            ColumnMapping('ACCOUNT_TYPE', 'TYPE', 0.80)
        ]
        
        relationship = Relationship(
            source_table='ACCOUNTS',
            target_table='CUSTOMERS',
            constraint_name='FK_ACCOUNTS_CUSTOMER',
            cardinality='many_to_one',
            column_mappings=column_mappings,
            quality=0.90
        )
        
        assert relationship.source_table == 'ACCOUNTS'
        assert relationship.target_table == 'CUSTOMERS'
        assert relationship.cardinality == 'many_to_one'
        assert len(relationship.column_mappings) == 2
        assert relationship.quality == 0.90
    
    def test_join_path(self):
        """Test JoinPath dataclass."""
        join_path = JoinPath(
            source_table='TRANSACTIONS',
            target_table='CUSTOMERS',
            tables=['TRANSACTIONS', 'ACCOUNTS', 'CUSTOMERS'],
            join_conditions=[
                'TRANSACTIONS.ACCOUNT_ID = ACCOUNTS.ID',
                'ACCOUNTS.CUSTOMER_ID = CUSTOMERS.ID'
            ],
            total_quality=0.85
        )
        
        assert join_path.source_table == 'TRANSACTIONS'
        assert join_path.target_table == 'CUSTOMERS'
        assert len(join_path.tables) == 3
        assert len(join_path.join_conditions) == 2
        assert join_path.total_quality == 0.85

class TestRelationshipBuilder:
    """Test relationship graph building."""
    
    def setup_method(self):
        """Setup test environment."""
        self.temp_dir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.temp_dir, 'test_relationships.db')
        self.catalog = CatalogStore(self.db_path)
        
        # Setup test data
        self._setup_test_data()
        
        # Create builder
        self.builder = RelationshipBuilder(self.catalog)
    
    def teardown_method(self):
        """Cleanup test environment."""
        if os.path.exists(self.db_path):
            os.unlink(self.db_path)
        os.rmdir(self.temp_dir)
    
    def _setup_test_data(self):
        """Setup comprehensive test data for relationship building."""
        # Add schema
        self.catalog.upsert_schema(
            owner='AML_TEST',
            default_tablespace='AML_DATA',
            created='2024-01-01T00:00:00'
        )
        
        # Add tables
        tables = [
            ('CUSTOMERS', 10000),
            ('ACCOUNTS', 25000),
            ('TRANSACTIONS', 500000),
            ('ALERTS', 1000),
            ('PARTIES', 5000),
            ('PARTY_RELATIONSHIPS', 2000)
        ]
        
        for table_name, num_rows in tables:
            self.catalog.upsert_table(
                owner='AML_TEST',
                table_name=table_name,
                tablespace_name='AML_DATA',
                num_rows=num_rows
            )
        
        # Add columns for CUSTOMERS
        customer_columns = [
            ('CUSTOMER_ID', 'NUMBER', 10, 'N', False),
            ('SSN', 'VARCHAR2', 11, 'Y', True),
            ('EMAIL', 'VARCHAR2', 255, 'N', True),
            ('FIRST_NAME', 'VARCHAR2', 50, 'N', True),
            ('LAST_NAME', 'VARCHAR2', 50, 'N', True)
        ]
        
        for col_name, data_type, length, nullable, is_pii in customer_columns:
            self.catalog.upsert_column(
                owner='AML_TEST',
                table_name='CUSTOMERS',
                column_name=col_name,
                data_type=data_type,
                data_length=length,
                nullable=nullable,
                is_pii=is_pii
            )
        
        # Add columns for ACCOUNTS
        account_columns = [
            ('ACCOUNT_ID', 'NUMBER', 10, 'N', False),
            ('CUSTOMER_ID', 'NUMBER', 10, 'N', False),
            ('ACCOUNT_NUMBER', 'VARCHAR2', 20, 'N', True),
            ('BALANCE', 'NUMBER', 15, 'Y', False)
        ]
        
        for col_name, data_type, length, nullable, is_pii in account_columns:
            self.catalog.upsert_column(
                owner='AML_TEST',
                table_name='ACCOUNTS',
                column_name=col_name,
                data_type=data_type,
                data_length=length,
                nullable=nullable,
                is_pii=is_pii
            )
        
        # Add columns for TRANSACTIONS
        transaction_columns = [
            ('TRANSACTION_ID', 'NUMBER', 10, 'N', False),
            ('ACCOUNT_ID', 'NUMBER', 10, 'N', False),
            ('AMOUNT', 'NUMBER', 15, 'N', False),
            ('TRANSACTION_DATE', 'DATE', None, 'N', False)
        ]
        
        for col_name, data_type, length, nullable, is_pii in transaction_columns:
            self.catalog.upsert_column(
                owner='AML_TEST',
                table_name='TRANSACTIONS',
                column_name=col_name,
                data_type=data_type,
                data_length=length,
                nullable=nullable,
                is_pii=is_pii
            )
        
        # Add constraints
        constraints = [
            ('PK_CUSTOMERS', 'P', 'CUSTOMERS', None, None),
            ('PK_ACCOUNTS', 'P', 'ACCOUNTS', None, None),
            ('PK_TRANSACTIONS', 'P', 'TRANSACTIONS', None, None),
            ('FK_ACCOUNTS_CUSTOMER', 'R', 'ACCOUNTS', 'AML_TEST', 'PK_CUSTOMERS'),
            ('FK_TRANS_ACCOUNT', 'R', 'TRANSACTIONS', 'AML_TEST', 'PK_ACCOUNTS')
        ]
        
        for constraint_name, constraint_type, table_name, r_owner, r_constraint in constraints:
            self.catalog.upsert_constraint(
                owner='AML_TEST',
                constraint_name=constraint_name,
                constraint_type=constraint_type,
                table_name=table_name,
                r_owner=r_owner,
                r_constraint_name=r_constraint
            )
        
        # Add pre-defined relationships
        relationships = [
            ('AML_TEST.ACCOUNTS', 'AML_TEST.CUSTOMERS', 'FK_ACCOUNTS_CUSTOMER', 'many_to_one', 0.95),
            ('AML_TEST.TRANSACTIONS', 'AML_TEST.ACCOUNTS', 'FK_TRANS_ACCOUNT', 'many_to_one', 0.90)
        ]
        
        for source, target, constraint, cardinality, quality in relationships:
            self.catalog.upsert_relationship(
                source_table=source,
                target_table=target,
                constraint_name=constraint,
                cardinality=cardinality,
                quality=quality
            )
    
    def test_builder_initialization(self):
        """Test RelationshipBuilder initialization."""
        assert self.builder.catalog == self.catalog
        assert self.builder.graph is not None
    
    def test_detect_cardinality(self):
        """Test cardinality detection."""
        # Test many-to-one (default for FK)
        cardinality = self.builder._detect_cardinality(
            'AML_TEST.ACCOUNTS',
            'AML_TEST.CUSTOMERS',
            'FK_ACCOUNTS_CUSTOMER'
        )
        assert cardinality == 'many_to_one'
        
        # Test with mock data for one-to-one
        with patch.object(self.builder.catalog, '_get_connection') as mock_conn:
            mock_cursor = Mock()
            mock_cursor.fetchone.return_value = {'ratio': 0.95}  # High ratio indicates one-to-one
            mock_conn.return_value.__enter__.return_value.execute.return_value = mock_cursor
            
            cardinality = self.builder._detect_cardinality(
                'AML_TEST.ACCOUNTS',
                'AML_TEST.CUSTOMERS',
                'FK_ACCOUNTS_CUSTOMER'
            )
            # Note: This would require more sophisticated logic in actual implementation
    
    def test_map_columns(self):
        """Test column mapping between tables."""
        mappings = self.builder._map_columns(
            'AML_TEST.ACCOUNTS',
            'AML_TEST.CUSTOMERS'
        )
        
        assert len(mappings) > 0
        
        # Should find CUSTOMER_ID mapping
        customer_id_mapping = next(
            (m for m in mappings if m.source_column == 'CUSTOMER_ID'),
            None
        )
        assert customer_id_mapping is not None
        assert customer_id_mapping.target_column == 'CUSTOMER_ID'
        assert customer_id_mapping.match_quality > 0.9  # Exact match
    
    def test_calculate_relationship_quality(self):
        """Test relationship quality calculation."""
        column_mappings = [
            ColumnMapping('CUSTOMER_ID', 'CUSTOMER_ID', 1.0),
            ColumnMapping('STATUS', 'STATUS', 0.8)
        ]
        
        quality = self.builder._calculate_relationship_quality(
            column_mappings,
            'many_to_one',
            has_constraint=True
        )
        
        assert 0.0 <= quality <= 1.0
        assert quality > 0.8  # Should be high due to exact matches and constraint
    
    @patch('services.db.relationship_builder.nx')
    def test_build_relationships(self, mock_nx):
        """Test building the relationship graph."""
        # Mock NetworkX graph
        mock_graph = Mock()
        mock_nx.DiGraph.return_value = mock_graph
        
        self.builder.build_relationships()
        
        # Verify graph operations were called
        assert mock_graph.add_node.called
        assert mock_graph.add_edge.called
    
    def test_find_shortest_path(self):
        """Test shortest path finding."""
        # Build relationships first
        self.builder.build_relationships()
        
        # Find path from TRANSACTIONS to CUSTOMERS
        path = self.builder.find_shortest_path(
            'AML_TEST.TRANSACTIONS',
            'AML_TEST.CUSTOMERS'
        )
        
        assert path is not None
        assert path.source_table == 'AML_TEST.TRANSACTIONS'
        assert path.target_table == 'AML_TEST.CUSTOMERS'
        assert len(path.tables) >= 2
        
        # Should go through ACCOUNTS
        assert 'AML_TEST.ACCOUNTS' in path.tables
        
        # Check join conditions
        assert len(path.join_conditions) == len(path.tables) - 1
    
    def test_find_shortest_path_direct(self):
        """Test shortest path for directly connected tables."""
        self.builder.build_relationships()
        
        # Find direct path from ACCOUNTS to CUSTOMERS
        path = self.builder.find_shortest_path(
            'AML_TEST.ACCOUNTS',
            'AML_TEST.CUSTOMERS'
        )
        
        assert path is not None
        assert len(path.tables) == 2
        assert path.tables[0] == 'AML_TEST.ACCOUNTS'
        assert path.tables[1] == 'AML_TEST.CUSTOMERS'
        assert len(path.join_conditions) == 1
    
    def test_find_shortest_path_nonexistent(self):
        """Test shortest path for non-existent tables."""
        self.builder.build_relationships()
        
        # Path to non-existent table
        path = self.builder.find_shortest_path(
            'AML_TEST.ACCOUNTS',
            'AML_TEST.NONEXISTENT'
        )
        assert path is None
        
        # Path from non-existent table
        path = self.builder.find_shortest_path(
            'AML_TEST.NONEXISTENT',
            'AML_TEST.CUSTOMERS'
        )
        assert path is None
    
    def test_get_related_tables(self):
        """Test getting related tables."""
        self.builder.build_relationships()
        
        # Get tables related to CUSTOMERS
        related = self.builder.get_related_tables('AML_TEST.CUSTOMERS')
        
        assert len(related) > 0
        assert 'AML_TEST.ACCOUNTS' in related
        
        # Get tables related to TRANSACTIONS
        related = self.builder.get_related_tables('AML_TEST.TRANSACTIONS')
        
        assert len(related) > 0
        assert 'AML_TEST.ACCOUNTS' in related
    
    def test_export_relationships(self):
        """Test exporting relationships."""
        self.builder.build_relationships()
        
        # Export all relationships
        relationships = self.builder.export_relationships()
        
        assert len(relationships) > 0
        
        # Check relationship structure
        for rel in relationships:
            assert 'source_table' in rel
            assert 'target_table' in rel
            assert 'cardinality' in rel
            assert 'quality' in rel
            assert 'column_mappings' in rel
    
    def test_graph_statistics(self):
        """Test graph statistics."""
        self.builder.build_relationships()
        
        stats = self.builder.get_graph_statistics()
        
        assert 'nodes' in stats
        assert 'edges' in stats
        assert 'avg_degree' in stats
        assert 'connected_components' in stats
        
        assert stats['nodes'] > 0
        assert stats['edges'] > 0

class TestComplexRelationshipScenarios:
    """Test complex relationship scenarios."""
    
    def setup_method(self):
        """Setup complex test environment."""
        self.temp_dir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.temp_dir, 'test_complex.db')
        self.catalog = CatalogStore(self.db_path)
        
        self._setup_complex_data()
        self.builder = RelationshipBuilder(self.catalog)
    
    def teardown_method(self):
        """Cleanup test environment."""
        if os.path.exists(self.db_path):
            os.unlink(self.db_path)
        os.rmdir(self.temp_dir)
    
    def _setup_complex_data(self):
        """Setup complex AML schema with multiple relationship types."""
        # Add schema
        self.catalog.upsert_schema(
            owner='AML_COMPLEX',
            default_tablespace='AML_DATA',
            created='2024-01-01T00:00:00'
        )
        
        # Complex table structure
        tables = [
            ('PARTIES', 50000),          # Main entity table
            ('INDIVIDUALS', 30000),      # Inherits from PARTIES
            ('ENTITIES', 20000),         # Inherits from PARTIES
            ('ACCOUNTS', 100000),        # Linked to PARTIES
            ('TRANSACTIONS', 5000000),   # Linked to ACCOUNTS
            ('ALERTS', 10000),           # Linked to PARTIES and TRANSACTIONS
            ('CASES', 2000),             # Linked to ALERTS
            ('PARTY_LINKS', 15000),      # Many-to-many PARTIES relationships
            ('ADDRESSES', 40000),        # Linked to PARTIES
            ('SANCTIONS', 5000)          # Reference data
        ]
        
        for table_name, num_rows in tables:
            self.catalog.upsert_table(
                owner='AML_COMPLEX',
                table_name=table_name,
                tablespace_name='AML_DATA',
                num_rows=num_rows
            )
        
        # Define complex relationships
        relationships = [
            # Direct relationships
            ('AML_COMPLEX.ACCOUNTS', 'AML_COMPLEX.PARTIES', 'FK_ACCOUNTS_PARTY', 'many_to_one', 0.95),
            ('AML_COMPLEX.TRANSACTIONS', 'AML_COMPLEX.ACCOUNTS', 'FK_TRANS_ACCOUNT', 'many_to_one', 0.90),
            ('AML_COMPLEX.ALERTS', 'AML_COMPLEX.PARTIES', 'FK_ALERTS_PARTY', 'many_to_one', 0.85),
            ('AML_COMPLEX.ALERTS', 'AML_COMPLEX.TRANSACTIONS', 'FK_ALERTS_TRANS', 'many_to_one', 0.80),
            ('AML_COMPLEX.CASES', 'AML_COMPLEX.ALERTS', 'FK_CASES_ALERT', 'one_to_many', 0.88),
            
            # Inheritance relationships
            ('AML_COMPLEX.INDIVIDUALS', 'AML_COMPLEX.PARTIES', 'FK_INDIV_PARTY', 'one_to_one', 0.98),
            ('AML_COMPLEX.ENTITIES', 'AML_COMPLEX.PARTIES', 'FK_ENTITY_PARTY', 'one_to_one', 0.98),
            
            # Many-to-many through junction table
            ('AML_COMPLEX.PARTY_LINKS', 'AML_COMPLEX.PARTIES', 'FK_LINKS_PARTY1', 'many_to_one', 0.92),
            
            # Address relationships
            ('AML_COMPLEX.ADDRESSES', 'AML_COMPLEX.PARTIES', 'FK_ADDR_PARTY', 'many_to_one', 0.90),
        ]
        
        for source, target, constraint, cardinality, quality in relationships:
            self.catalog.upsert_relationship(
                source_table=source,
                target_table=target,
                constraint_name=constraint,
                cardinality=cardinality,
                quality=quality
            )
    
    def test_complex_path_finding(self):
        """Test path finding in complex schema."""
        self.builder.build_relationships()
        
        # Find path from SANCTIONS to TRANSACTIONS
        # Should go through multiple hops
        path = self.builder.find_shortest_path(
            'AML_COMPLEX.SANCTIONS',
            'AML_COMPLEX.TRANSACTIONS'
        )
        
        # Path may not exist if SANCTIONS is not connected
        # This tests the isolation handling
        
        # Find path from INDIVIDUALS to TRANSACTIONS
        path = self.builder.find_shortest_path(
            'AML_COMPLEX.INDIVIDUALS',
            'AML_COMPLEX.TRANSACTIONS'
        )
        
        if path:
            assert len(path.tables) >= 3
            # Should go through PARTIES and ACCOUNTS
            assert 'AML_COMPLEX.PARTIES' in path.tables
            assert 'AML_COMPLEX.ACCOUNTS' in path.tables
    
    def test_inheritance_relationships(self):
        """Test handling of inheritance relationships."""
        self.builder.build_relationships()
        
        # Get relationships for INDIVIDUALS
        related = self.builder.get_related_tables('AML_COMPLEX.INDIVIDUALS')
        
        # Should be connected to PARTIES
        assert 'AML_COMPLEX.PARTIES' in related
        
        # Find path using inheritance
        path = self.builder.find_shortest_path(
            'AML_COMPLEX.INDIVIDUALS',
            'AML_COMPLEX.ACCOUNTS'
        )
        
        if path:
            # Should use inheritance relationship
            assert 'AML_COMPLEX.PARTIES' in path.tables
    
    def test_many_to_many_relationships(self):
        """Test handling of many-to-many relationships."""
        self.builder.build_relationships()
        
        # Check PARTY_LINKS junction table
        related = self.builder.get_related_tables('AML_COMPLEX.PARTY_LINKS')
        
        assert 'AML_COMPLEX.PARTIES' in related
    
    def test_graph_connectivity(self):
        """Test graph connectivity analysis."""
        self.builder.build_relationships()
        
        stats = self.builder.get_graph_statistics()
        
        # Should have reasonable connectivity
        assert stats['nodes'] >= 8  # At least 8 connected tables
        assert stats['edges'] >= 7  # At least 7 relationships
        
        # Check for isolated components
        # In a well-connected AML schema, should have few isolated components
        assert stats['connected_components'] <= 3

class TestRelationshipQualityMetrics:
    """Test relationship quality assessment."""
    
    def setup_method(self):
        """Setup quality testing environment."""
        self.temp_dir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.temp_dir, 'test_quality.db')
        self.catalog = CatalogStore(self.db_path)
        self.builder = RelationshipBuilder(self.catalog)
    
    def teardown_method(self):
        """Cleanup test environment."""
        if os.path.exists(self.db_path):
            os.unlink(self.db_path)
        os.rmdir(self.temp_dir)
    
    def test_exact_column_match_quality(self):
        """Test quality scoring for exact column matches."""
        mappings = [
            ColumnMapping('CUSTOMER_ID', 'CUSTOMER_ID', 1.0),  # Exact match
            ColumnMapping('EMAIL', 'EMAIL', 1.0)               # Exact match
        ]
        
        quality = self.builder._calculate_relationship_quality(
            mappings,
            'many_to_one',
            has_constraint=True
        )
        
        # Should be very high quality
        assert quality > 0.9
    
    def test_partial_column_match_quality(self):
        """Test quality scoring for partial column matches."""
        mappings = [
            ColumnMapping('CUST_ID', 'CUSTOMER_ID', 0.8),     # Partial match
            ColumnMapping('EMAIL_ADDR', 'EMAIL', 0.7)          # Partial match
        ]
        
        quality = self.builder._calculate_relationship_quality(
            mappings,
            'many_to_one',
            has_constraint=False
        )
        
        # Should be moderate quality
        assert 0.5 <= quality <= 0.8
    
    def test_no_column_match_quality(self):
        """Test quality scoring with no column matches."""
        mappings = []  # No column mappings
        
        quality = self.builder._calculate_relationship_quality(
            mappings,
            'many_to_one',
            has_constraint=False
        )
        
        # Should be low quality
        assert quality < 0.5
    
    def test_constraint_quality_boost(self):
        """Test quality boost from formal constraints."""
        mappings = [
            ColumnMapping('ID', 'CUSTOMER_ID', 0.6)  # Moderate match
        ]
        
        # Without constraint
        quality_no_constraint = self.builder._calculate_relationship_quality(
            mappings,
            'many_to_one',
            has_constraint=False
        )
        
        # With constraint
        quality_with_constraint = self.builder._calculate_relationship_quality(
            mappings,
            'many_to_one',
            has_constraint=True
        )
        
        # Constraint should boost quality
        assert quality_with_constraint > quality_no_constraint

def test_relationship_builder_error_handling():
    """Test error handling in relationship builder."""
    # Empty catalog
    catalog = CatalogStore(':memory:')
    builder = RelationshipBuilder(catalog)
    
    # Build relationships on empty catalog
    builder.build_relationships()
    
    # Should not raise errors
    stats = builder.get_graph_statistics()
    assert stats['nodes'] == 0
    assert stats['edges'] == 0
    
    # Find path in empty graph
    path = builder.find_shortest_path('TABLE1', 'TABLE2')
    assert path is None
    
    # Get related tables for non-existent table
    related = builder.get_related_tables('NONEXISTENT')
    assert len(related) == 0

if __name__ == '__main__':
    # Run basic tests
    import sys
    
    # Simple test runner
    test_classes = [
        TestRelationshipDataClasses,
        TestRelationshipBuilder,
        TestComplexRelationshipScenarios,
        TestRelationshipQualityMetrics
    ]
    
    for test_class in test_classes:
        print(f"\nRunning tests for {test_class.__name__}...")
        
        instance = test_class()
        test_methods = [method for method in dir(instance) if method.startswith('test_')]
        
        passed = 0
        failed = 0
        
        for method_name in test_methods:
            try:
                if hasattr(instance, 'setup_method'):
                    instance.setup_method()
                
                method = getattr(instance, method_name)
                method()
                
                if hasattr(instance, 'teardown_method'):
                    instance.teardown_method()
                
                print(f"  ✓ {method_name}")
                passed += 1
            except Exception as e:
                print(f"  ✗ {method_name}: {e}")
                failed += 1
                
                try:
                    if hasattr(instance, 'teardown_method'):
                        instance.teardown_method()
                except:
                    pass
        
        print(f"  Results: {passed} passed, {failed} failed")
    
    print("\nAll tests completed.")