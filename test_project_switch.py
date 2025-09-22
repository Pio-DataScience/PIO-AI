#!/usr/bin/env python3
"""Test project switch with debug output."""

import sys
from pathlib import Path

# Add the PIO-AI root to path
ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

def test_project_switch():
    """Test project switch step by step."""
    
    print("=== Testing Project Switch ===")
    
    try:
        # Test manifest reader
        print("1. Testing manifest reader:")
        from services.ingest.manifest_reader import get_project_by_name
        project = get_project_by_name('AI_AML')
        print(f"   Project keys: {list(project.keys())}")
        print(f"   Root path: {project['root_path']}")
        
        # Test fs_tools access
        print("\n2. Testing fs_tools access:")
        from services.tools_api.fs_tools import file_exists
        result = file_exists('AI_AML', 'README.md')
        print(f"   README.md exists: {result}")
        
        # Test the exact scenario from chat
        print("\n3. Testing retrieval scenario:")
        from services.retriever.hybrid import HybridRetriever
        retriever = HybridRetriever()
        
        # This is what happens when you switch projects in chat
        hits = retriever.retrieve("", 'AI_AML', max_results=1)
        print(f"   Initial retrieve hits: {len(hits)}")
        
        # Test with actual query
        hits = retriever.retrieve("Tell me about the AI AML system", 'AI_AML', max_results=3)
        print(f"   Query hits: {len(hits)}")
        for hit in hits:
            print(f"     - {hit.path}: {hit.score:.3f}")
        
    except Exception as e:
        print(f"ERROR: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_project_switch()