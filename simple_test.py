#!/usr/bin/env python3
"""Simple test of chat functionality."""

import sys
from pathlib import Path

# Add the PIO-AI root to path
ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

def main():
    """Test basic chat functionality."""
    try:
        # Import chat components
        from services.llm.answer import answer_with_context
        from services.ingest.manifest_reader import get_project_by_name
        
        print("Testing basic retrieval...")
        
        # Set project
        project = "AI_AML"
        
        # Test basic query
        query = "Tell me about the AI AML system"
        
        print(f"Project: {project}")
        print(f"Query: {query}")
        
        # Call answer_with_context directly
        response = answer_with_context(
            query=query,
            project=project,
            path="",
            line=0
        )
        
        print(f"\nResponse type: {type(response)}")
        print(f"Response: {response}")
        
        if isinstance(response, dict):
            answer = response.get('answer', str(response))
            print(f"Answer length: {len(answer)}")
            print(f"Answer preview: {answer[:200]}...")
        else:
            print(f"Response content: {str(response)[:200]}...")
        
    except Exception as e:
        print(f"ERROR: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()