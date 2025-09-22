"""
PIO-AI: Local, offline-friendly RAG system for code and project analysis.

This package provides:
- AST symbol indexing
- Call & import graph analysis  
- BM25 keyword search
- FAISS vector search
- Hybrid retrieval system
- Tools API for file/schema access
- LLM integration with local/OpenAI providers
- FastAPI server for query processing
"""

__version__ = "0.1.0"

from pathlib import Path

# Package root for all path anchoring
PACKAGE_ROOT = Path(__file__).resolve().parent