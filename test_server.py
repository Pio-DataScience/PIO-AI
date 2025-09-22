"""
Minimal production API server to test basic functionality.
"""

import os
import sys
from pathlib import Path

# Add package to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from fastapi import FastAPI
import uvicorn

# Create minimal app
app = FastAPI(
    title="PIO-AI Minimal Test API",
    description="Minimal test server for debugging",
    version="1.0.0"
)

@app.get("/")
async def root():
    return {"message": "PIO-AI Minimal Test API is running"}

@app.get("/health")
async def health():
    return {"status": "healthy", "message": "All systems operational"}

@app.get("/test-imports")
async def test_imports():
    """Test if all imports work."""
    results = {}
    
    try:
        from services.llm.answer import answer_query
        results["llm"] = "success"
    except Exception as e:
        results["llm"] = f"error: {str(e)}"
    
    try:
        from services.db.catalog_store import CatalogStore
        results["catalog"] = "success"
    except Exception as e:
        results["catalog"] = f"error: {str(e)}"
    
    try:
        from services.db.graph_store import ProductionGraphStore
        results["graph"] = "success"
    except Exception as e:
        results["graph"] = f"error: {str(e)}"
    
    try:
        import chromadb
        results["chromadb"] = "success"
    except Exception as e:
        results["chromadb"] = f"error: {str(e)}"
    
    return {"import_tests": results}

if __name__ == "__main__":
    host = "127.0.0.1"
    port = 8080
    
    print(f"🚀 Starting PIO-AI Minimal Test API on {host}:{port}")
    print(f"📚 Documentation available at http://{host}:{port}/docs")
    
    uvicorn.run(
        "test_server:app",
        host=host,
        port=port,
        reload=False,
        log_level="info"
    )