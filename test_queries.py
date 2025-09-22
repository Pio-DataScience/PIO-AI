#!/usr/bin/env python3
"""Test various search queries."""

import sys
from pathlib import Path

# Add the PIO-AI root to path
ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from services.indexer.bm25_index import search_bm25

test_queries = ['AML', 'outlier', 'detection', 'model', 'system']
for q in test_queries:
    results = search_bm25('AI_AML', q, 3)
    print(f'{q}: {len(results)} results')
    for r in results[:1]:
        print(f'  - {r["path"]}')