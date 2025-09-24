"""
Simple test to debug the exact execution path for schema queries
"""
import asyncio
import sys
import uuid
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent
sys.path.append(str(project_root))

from services.agents.modern_orchestrator import ModernAgentOrchestrator

async def test_schema_path():
    """Test schema path specifically."""
    print("🔍 Testing Schema Path Debug...")
    
    try:
        from services.llm.provider import LLMManager
        from services.agents.modern_orchestrator import ModernAgentOrchestrator
        
        # Initialize components (copy from working test)
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
        print(f"✅ Modern orchestrator initialized")
        
    except Exception as e:
        print(f"❌ Failed to initialize orchestrator: {e}")
        return
    
    session_id = str(uuid.uuid4())
    query = "tell me about PIO_ACCOUNTS table"
    
    print(f"\n📝 Query: '{query}'")
    print(f"📝 Session: {session_id}")
    
    try:
        # Process query and print each step
        result = await orchestrator.process_query(query, session_id)
        
        print(f"\n✅ Final Result:")
        print(f"   Result keys: {list(result.keys()) if result else 'None'}")
        if result:
            print(f"   Response: {result.get('response', 'No response')[:200]}...")
            print(f"   Intent: {result.get('intent', 'No intent')}")
            print(f"   Confidence: {result.get('confidence', 'No confidence')}")
            print(f"   Execution Path: {result.get('execution_path', 'No path')}")
            print(f"   Tools: {result.get('tools_used', 'No tools')}")
        else:
            print("   No result returned")
        
    except Exception as e:
        print(f"\n❌ Error during processing: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(test_schema_path())