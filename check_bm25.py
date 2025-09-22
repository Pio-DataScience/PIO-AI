#!/usr/bin/env python3
"""Check BM25 result format."""

import sys
from pathlib import Path

# Add the PIO-AI root to path
ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from services.indexer.bm25_index import search_bm25

results = search_bm25('AI_AML', 'class', top_k=2)
print('BM25 results:')
for r in results:
    print(f'- path: {r["path"]}, kind: {r["kind"]}, score: {r["score"]:.3f}')