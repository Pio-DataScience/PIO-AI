#!/usr/bin/env python3
"""
Production Setup Script for AML Database System
Installs and configures production-grade components.
"""

import os
import sys
import subprocess
import logging
from typing import List, Dict, Any
import yaml

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class ProductionSetup:
    """Setup production environment for AML database system."""
    
    def __init__(self):
        self.project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        self.requirements = {
            'core': [
                'torch>=2.0.0',
                'transformers>=4.30.0',
                'sentence-transformers>=2.2.2',
                'chromadb>=0.4.0',
                'neo4j>=5.12.0',
                'tqdm>=4.65.0'
            ],
            'optional': [
                'faiss-cpu>=1.7.4',  # Alternative to ChromaDB
                'networkx>=3.1',     # Graph algorithms
                'plotly>=5.15.0',    # Visualization
                'dash>=2.12.0'       # Dashboard
            ]
        }
    
    def check_python_version(self):
        """Check Python version compatibility."""
        logger.info("Checking Python version...")
        
        version = sys.version_info
        if version.major < 3 or (version.major == 3 and version.minor < 8):
            raise RuntimeError("Python 3.8+ required for production deployment")
        
        logger.info(f"✅ Python {version.major}.{version.minor}.{version.micro} compatible")
    
    def install_production_packages(self):
        """Install production packages."""
        logger.info("Installing production packages...")
        
        all_packages = self.requirements['core'] + self.requirements['optional']
        
        for package in all_packages:
            try:
                logger.info(f"Installing {package}...")
                subprocess.run(
                    [sys.executable, '-m', 'pip', 'install', package],
                    check=True,
                    capture_output=True,
                    text=True
                )
                logger.info(f"✅ {package} installed successfully")
            except subprocess.CalledProcessError as e:
                logger.warning(f"⚠️ Failed to install {package}: {e}")
                logger.info(f"Error output: {e.stderr}")
    
    def setup_directories(self):
        """Create production directory structure."""
        logger.info("Setting up production directories...")
        
        directories = [
            'warehouse/vectors',
            'warehouse/models',
            'warehouse/cache',
            'logs/production',
            'backups/catalog',
            'backups/vectors',
            'backups/graph'
        ]
        
        for directory in directories:
            full_path = os.path.join(self.project_root, directory)
            os.makedirs(full_path, exist_ok=True)
            logger.info(f"✅ Created directory: {directory}")
    
    def download_production_models(self):
        """Download and cache production models."""
        logger.info("Downloading production models...")
        
        try:
            from sentence_transformers import SentenceTransformer
            
            # Download BGE-large-en-v1.5
            logger.info("Downloading BGE-large-en-v1.5 (this may take several minutes)...")
            model = SentenceTransformer("BAAI/bge-large-en-v1.5")
            
            # Save to local cache
            cache_dir = os.path.join(self.project_root, 'warehouse', 'models', 'bge-large-en-v1.5')
            model.save(cache_dir)
            logger.info(f"✅ BGE model cached to: {cache_dir}")
            
        except ImportError:
            logger.warning("⚠️ sentence-transformers not available, skipping model download")
        except Exception as e:
            logger.error(f"❌ Failed to download models: {e}")
    
    def setup_neo4j_docker(self):
        """Setup Neo4j using Docker (recommended for production)."""
        logger.info("Setting up Neo4j with Docker...")
        
        docker_compose = """
version: '3.8'
services:
  neo4j:
    image: neo4j:5.12-community
    container_name: aml-neo4j
    ports:
      - "7474:7474"  # HTTP
      - "7687:7687"  # Bolt
    environment:
      - NEO4J_AUTH=neo4j/production_password
      - NEO4J_PLUGINS=["apoc"]
      - NEO4J_dbms_security_procedures_unrestricted=apoc.*
      - NEO4J_dbms_memory_heap_initial_size=2G
      - NEO4J_dbms_memory_heap_max_size=4G
      - NEO4J_dbms_memory_pagecache_size=2G
    volumes:
      - neo4j_data:/data
      - neo4j_logs:/logs
      - neo4j_import:/var/lib/neo4j/import
      - neo4j_plugins:/plugins
    restart: unless-stopped

volumes:
  neo4j_data:
  neo4j_logs:
  neo4j_import:
  neo4j_plugins:
"""
        
        compose_path = os.path.join(self.project_root, 'docker-compose.neo4j.yml')
        with open(compose_path, 'w') as f:
            f.write(docker_compose)
        
        logger.info(f"✅ Docker Compose file created: {compose_path}")
        logger.info("🐳 To start Neo4j: docker-compose -f docker-compose.neo4j.yml up -d")
        logger.info("🌐 Neo4j Browser: http://localhost:7474")
        logger.info("🔑 Default credentials: neo4j/production_password")
    
    def update_configuration(self):
        """Update configuration files for production."""
        logger.info("Updating configuration for production...")
        
        # Update graph.yaml with production settings
        graph_config_path = os.path.join(self.project_root, 'config', 'graph.yaml')
        
        if os.path.exists(graph_config_path):
            with open(graph_config_path, 'r') as f:
                config = yaml.safe_load(f)
            
            # Update with production values
            config['neo4j']['password'] = 'production_password'
            config['settings']['batch_size'] = 2000  # Higher for production
            
            with open(graph_config_path, 'w') as f:
                yaml.dump(config, f, default_flow_style=False)
            
            logger.info("✅ Updated graph.yaml for production")
        
        # Create production logging config
        logging_config = {
            'version': 1,
            'disable_existing_loggers': False,
            'formatters': {
                'standard': {
                    'format': '%(asctime)s [%(levelname)s] %(name)s: %(message)s'
                },
                'detailed': {
                    'format': '%(asctime)s [%(levelname)s] %(name)s:%(lineno)d: %(message)s'
                }
            },
            'handlers': {
                'console': {
                    'level': 'INFO',
                    'class': 'logging.StreamHandler',
                    'formatter': 'standard'
                },
                'file': {
                    'level': 'DEBUG',
                    'class': 'logging.handlers.RotatingFileHandler',
                    'filename': 'logs/production/aml_system.log',
                    'maxBytes': 10485760,  # 10MB
                    'backupCount': 5,
                    'formatter': 'detailed'
                }
            },
            'loggers': {
                '': {  # root logger
                    'handlers': ['console', 'file'],
                    'level': 'INFO',
                    'propagate': False
                }
            }
        }
        
        logging_config_path = os.path.join(self.project_root, 'config', 'logging.yaml')
        with open(logging_config_path, 'w') as f:
            yaml.dump(logging_config, f, default_flow_style=False)
        
        logger.info("✅ Created production logging configuration")
    
    def create_production_scripts(self):
        """Create production management scripts."""
        logger.info("Creating production management scripts...")
        
        # Production startup script
        startup_script = """#!/bin/bash
# Production AML Database System Startup Script

echo "🚀 Starting AML Database System (Production)"

# Check if Neo4j is running
if ! docker ps | grep -q aml-neo4j; then
    echo "Starting Neo4j..."
    docker-compose -f docker-compose.neo4j.yml up -d
    sleep 10
fi

# Verify connections
echo "Verifying connections..."
python -c "
import sys
sys.path.append('.')
from services.db.graph_store import ProductionGraphStore
try:
    graph = ProductionGraphStore(uri='neo4j://localhost:7687', user='neo4j', password='production_password')
    with graph:
        stats = graph.get_graph_statistics()
        print(f'✅ Neo4j connected: {stats.get(\"total_nodes\", 0)} nodes')
except Exception as e:
    print(f'❌ Neo4j connection failed: {e}')
"

echo "✅ AML Database System ready for production"
"""
        
        startup_path = os.path.join(self.project_root, 'scripts', 'production_startup.sh')
        with open(startup_path, 'w') as f:
            f.write(startup_script)
        
        # Make executable
        os.chmod(startup_path, 0o755)
        
        logger.info("✅ Created production startup script")
    
    def run_setup(self):
        """Run complete production setup."""
        logger.info("="*60)
        logger.info("🚀 PRODUCTION AML DATABASE SETUP")
        logger.info("="*60)
        
        try:
            self.check_python_version()
            self.setup_directories()
            self.install_production_packages()
            self.download_production_models()
            self.setup_neo4j_docker()
            self.update_configuration()
            self.create_production_scripts()
            
            logger.info("="*60)
            logger.info("✅ PRODUCTION SETUP COMPLETED SUCCESSFULLY")
            logger.info("="*60)
            
            logger.info("Next steps:")
            logger.info("1. Start Neo4j: docker-compose -f docker-compose.neo4j.yml up -d")
            logger.info("2. Build catalog: python scripts/41_build_aml_catalog.py")
            logger.info("3. Generate embeddings: python scripts/42_embed_aml_catalog.py")
            logger.info("4. Build graph: python scripts/43_build_production_graph.py")
            logger.info("5. Start API server: python scripts/40_serve_api.py")
            
        except Exception as e:
            logger.error(f"❌ Production setup failed: {e}")
            raise

def main():
    """Main entry point."""
    setup = ProductionSetup()
    setup.run_setup()

if __name__ == "__main__":
    main()