#!/usr/bin/env python3
"""
Simple test to verify the updated modern orchestrator works with vector search.
"""

import sys
import os
import asyncio
from pathlib import Path

# Add the project root to Python path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

async def test_schema_query():
    """Test schema queries with the updated modern orchestrator."""
    print("🚀 Testing Updated Modern Orchestrator...")
    print("=" * 50)
    
    try:
        from services.llm.provider import LLMManager
        from services.agents.modern_orchestrator import ModernAgentOrchestrator
        
        # Initialize components
        llm_manager = LLMManager()
        print(f"✅ LLM Manager initialized")
        
        # Configure the modern orchestrator
        config = {
            "llm": {"provider": "cohere"},
            "memory_path": "memory/sessions",
            "schema_db_path": "indexes/graph/AI_AML.sqlite",
            "db_config": {}
        }
        
        orchestrator = ModernAgentOrchestrator(config)
        print("✅ Modern orchestrator initialized")
        
        # Test the schema query that was failing
        test_queries = [
            "tell me about this table in details PIO_ACCOUNTS",
            "what are your capabilities?",
            "hello"
        ]
        
        for i, test_query in enumerate(test_queries, 1):
            print(f"\n📝 Test {i}: '{test_query}'")
            print("-" * 40)
            
            try:
                import uuid
                session_id = str(uuid.uuid4())
                response = await orchestrator.process_query(test_query, session_id=session_id)
                
                print(f"✅ Response received:")
                print(f"   Answer: {response['response'][:200]}...")
                print(f"   Intent: {response.get('intent', 'unknown')}")
                print(f"   Confidence: {response.get('confidence_score', 0):.2f}")
                print(f"   Tools Used: {response.get('tools_used', [])}")
                
                if response.get("error"):
                    print(f"   ⚠️ Error: {response['error']}")
                    
            except Exception as e:
                print(f"❌ Test failed: {e}")
                import traceback
                traceback.print_exc()
        
        print(f"\n🏁 Testing completed!")
        return True
        
    except Exception as e:
        print(f"❌ Setup failed: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    asyncio.run(test_schema_query())