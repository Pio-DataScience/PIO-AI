"""
Minimal test server to check imports.
"""

import os
import sys
from pathlib import Path

# Add package to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

print("Testing imports...")

try:
    from fastapi import FastAPI
    print("✅ FastAPI import successful")
except ImportError as e:
    print(f"❌ FastAPI import failed: {e}")

try:
    from services.llm.answer import answer_query, answer_simple, answer_with_context
    print("✅ LLM answer imports successful")
except ImportError as e:
    print(f"❌ LLM answer imports failed: {e}")

try:
    from services.retriever.hybrid import retrieve, HybridRetriever
    print("✅ Hybrid retriever imports successful")
except ImportError as e:
    print(f"❌ Hybrid retriever imports failed: {e}")

try:
    from services.db.catalog_store import CatalogStore
    print("✅ Catalog store import successful")
except ImportError as e:
    print(f"❌ Catalog store import failed: {e}")

try:
    from services.db.graph_store import ProductionGraphStore
    print("✅ Graph store import successful")
except ImportError as e:
    print(f"❌ Graph store import failed: {e}")

try:
    import chromadb
    print("✅ ChromaDB import successful")
except ImportError as e:
    print(f"❌ ChromaDB import failed: {e}")

print("All import tests completed.")