#!/usr/bin/env python3
"""
Script 41: Build AML Catalog
Harvest Oracle metadata for AML domain and store in local catalog.
"""

import os
import sys
import argparse
import yaml
import logging
from datetime import datetime
from typing import Dict, Any

# Add project root to path
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)

from services.db import (
    initialize_connection_pool, 
    ConnectionConfig, 
    CatalogStore,
    MetadataHarvester,
    HarvestConfig
)

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
    
    # Resolve environment variables
    oracle_config = config['oracle'].copy()
    for key, value in oracle_config.items():
        if isinstance(value, str) and value.startswith('${') and value.endswith('}'):
            env_var = value[2:-1]
            oracle_config[key] = os.environ.get(env_var)
            if oracle_config[key] is None:
                raise ValueError(f"Environment variable {env_var} not set")
    
    config['oracle'] = oracle_config
    return config

def create_connection_config(oracle_config: Dict[str, Any]) -> ConnectionConfig:
    """Create connection configuration from config dict."""
    return ConnectionConfig(
        dsn=oracle_config['dsn'],
        user=oracle_config['user'],
        password=oracle_config['password'],
        use_dba_views=oracle_config.get('use_dba_views', True),
        pool_min=oracle_config.get('pool_min', 1),
        pool_max=oracle_config.get('pool_max', 4),
        stmt_cache=oracle_config.get('stmt_cache', 50),
        fetch_arraysize=oracle_config.get('fetch_arraysize', 1000),
        connect_timeout=oracle_config.get('connect_timeout', 30),
        query_timeout=oracle_config.get('query_timeout', 300),
        retry_attempts=oracle_config.get('retry_attempts', 3),
        retry_backoff_factor=oracle_config.get('retry_backoff_factor', 2.0),
        circuit_breaker_failure_threshold=oracle_config.get('circuit_breaker_failure_threshold', 5),
        circuit_breaker_reset_timeout=oracle_config.get('circuit_breaker_reset_timeout', 60)
    )

def create_harvest_config(aml_config: Dict[str, Any]) -> HarvestConfig:
    """Create harvest configuration from config dict."""
    return HarvestConfig(
        owners=aml_config.get('owners', []),
        name_patterns=aml_config.get('name_patterns', []),
        exclude_patterns=aml_config.get('exclude_patterns', []),
        use_dba_views=True,  # Will be set from oracle config
        batch_size=1000
    )

def test_connection(conn_config: ConnectionConfig) -> bool:
    """Test Oracle connection."""
    try:
        initialize_connection_pool(conn_config)
        from services.db import get_connection_pool
        
        pool = get_connection_pool()
        health = pool.test_connection()
        
        if health['status'] == 'healthy':
            logger.info(f"Oracle connection successful - response time: {health['response_time_ms']:.2f}ms")
            return True
        else:
            logger.error(f"Oracle connection failed: {health.get('error', 'Unknown error')}")
            return False
    except Exception as e:
        logger.error(f"Failed to test Oracle connection: {e}")
        return False

def test_catalog(catalog_path: str) -> bool:
    """Test catalog database connection."""
    try:
        catalog = CatalogStore(catalog_path)
        health = catalog.health_check()
        
        if health['status'] == 'healthy':
            logger.info(f"Catalog connection successful - {health['database_tables']} tables")
            return True
        else:
            logger.error(f"Catalog connection failed: {health.get('error', 'Unknown error')}")
            return False
    except Exception as e:
        logger.error(f"Failed to test catalog connection: {e}")
        return False

def harvest_metadata(config: Dict[str, Any], pattern: str = None, dry_run: bool = False) -> Dict[str, Any]:
    """
    Harvest AML metadata from Oracle.
    
    Args:
        config: Database configuration
        pattern: Optional specific pattern to harvest
        dry_run: If True, don't actually store data
        
    Returns:
        Harvest statistics
    """
    start_time = datetime.utcnow()
    
    # Setup connection pool
    conn_config = create_connection_config(config['oracle'])
    initialize_connection_pool(conn_config)
    
    # Setup catalog
    catalog_path = config['catalog']['path']
    if not os.path.isabs(catalog_path):
        catalog_path = os.path.join(project_root, catalog_path)
    
    catalog = CatalogStore(catalog_path)
    
    # Setup harvester
    harvest_config = create_harvest_config(config['aml'])
    harvest_config.use_dba_views = config['oracle']['use_dba_views']
    
    # If specific pattern provided, use it instead of config patterns
    if pattern:
        harvest_config.name_patterns = [pattern]
    
    harvester = MetadataHarvester(harvest_config, catalog)
    
    if dry_run:
        logger.info("DRY RUN: Would harvest with config:")
        logger.info(f"  Owners: {harvest_config.owners}")
        logger.info(f"  Patterns: {harvest_config.name_patterns}")
        logger.info(f"  Exclude: {harvest_config.exclude_patterns}")
        return {"dry_run": True}
    
    # Perform harvest
    logger.info("Starting AML metadata harvest...")
    stats = harvester.harvest_aml_metadata()
    
    end_time = datetime.utcnow()
    duration = (end_time - start_time).total_seconds()
    
    stats['duration_seconds'] = duration
    stats['start_time'] = start_time.isoformat()
    stats['end_time'] = end_time.isoformat()
    
    logger.info(f"Harvest completed in {duration:.2f} seconds")
    logger.info(f"Results: {stats}")
    
    return stats

def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Harvest Oracle metadata for AML domain",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Harvest all AML metadata according to config
  python scripts/41_build_aml_catalog.py
  
  # Test connections only
  python scripts/41_build_aml_catalog.py --test-only
  
  # Harvest specific pattern
  python scripts/41_build_aml_catalog.py --pattern "PIO_AML_%"
  
  # Dry run to see what would be harvested
  python scripts/41_build_aml_catalog.py --dry-run
  
  # Verbose logging
  python scripts/41_build_aml_catalog.py --verbose
        """
    )
    
    parser.add_argument(
        '--pattern', 
        help='Specific table name pattern to harvest (overrides config patterns)'
    )
    parser.add_argument(
        '--test-only', 
        action='store_true',
        help='Test connections and exit'
    )
    parser.add_argument(
        '--dry-run', 
        action='store_true',
        help='Show what would be harvested without actually doing it'
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
        
        # Test connections
        logger.info("Testing Oracle connection...")
        conn_config = create_connection_config(config['oracle'])
        if not test_connection(conn_config):
            sys.exit(1)
        
        catalog_path = config['catalog']['path']
        if not os.path.isabs(catalog_path):
            catalog_path = os.path.join(project_root, catalog_path)
        
        logger.info("Testing catalog database...")
        if not test_catalog(catalog_path):
            sys.exit(1)
        
        if args.test_only:
            logger.info("Connection tests passed. Exiting.")
            return
        
        # Perform harvest
        stats = harvest_metadata(config, args.pattern, args.dry_run)
        
        if not args.dry_run:
            logger.info("="*50)
            logger.info("HARVEST SUMMARY")
            logger.info("="*50)
            logger.info(f"Tables by owner: {stats.get('tables_by_owner', 0)}")
            logger.info(f"Tables by pattern: {stats.get('tables_by_pattern', 0)}")
            logger.info(f"Views by owner: {stats.get('views_by_owner', 0)}")
            logger.info(f"Views by pattern: {stats.get('views_by_pattern', 0)}")
            logger.info(f"Total objects: {stats.get('total_objects', 0)}")
            logger.info(f"Duration: {stats.get('duration_seconds', 0):.2f} seconds")
            
        logger.info("Catalog build completed successfully!")
        
    except KeyboardInterrupt:
        logger.info("Operation cancelled by user")
        sys.exit(1)
    except Exception as e:
        logger.error(f"Error building catalog: {e}", exc_info=args.verbose)
        sys.exit(1)

if __name__ == '__main__':
    main()