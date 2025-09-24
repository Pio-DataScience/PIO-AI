#!/usr/bin/env python3
"""
Debug script to test vector retrieval and LLM conversation.
"""

import sys
import os
from pathlib import Path

# Add the project root to Python path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

def test_vector_retrieval():
    """Test vector-only retrieval system."""
    print("🔍 Testing Vector Retrieval System...")
    
    try:
        from services.agents.langgraph_orchestrator import VectorOnlyRetriever
        
        # Initialize retriever
        retriever = VectorOnlyRetriever()
        
        if not retriever.bge_model:
            print("❌ BGE model not loaded")
            return False
            
        if not retriever.collections:
            print("❌ No ChromaDB collections loaded")
            return False
            
        print(f"✅ Vector retriever initialized with {len(retriever.collections)} collections:")
        for name, collection in retriever.collections.items():
            print(f"   - {name}: {collection.count()} documents")
        
        # Test search
        test_query = "PIO_ACCOUNTS table structure columns"
        print(f"\n🔍 Testing search: '{test_query}'")
        
        results = retriever.semantic_search(test_query, max_results=5)
        
        if results:
            print(f"✅ Found {len(results)} results:")
            for i, result in enumerate(results[:3], 1):
                print(f"   {i}. Score: {result['similarity_score']:.3f}")
                print(f"      Collection: {result['collection']}")
                print(f"      Content: {result['content'][:100]}...")
                print()
        else:
            print("❌ No results found")
            return False
            
        return True
        
    except Exception as e:
        print(f"❌ Vector retrieval test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_llm_provider():
    """Test LLM provider functionality."""
    print("\n🤖 Testing LLM Provider...")
    
    try:
        from services.llm.provider import LLMManager
        
        # Initialize LLM manager
        llm_manager = LLMManager()
        
        print(f"✅ LLM Manager initialized with default provider: {llm_manager.default_provider}")
        print(f"   Available providers: {list(llm_manager.providers.keys())}")
        
        # Check which providers are available
        available_providers = []
        for name, provider in llm_manager.providers.items():
            if provider.is_available():
                available_providers.append(name)
                print(f"   ✅ {name}: Available")
            else:
                print(f"   ❌ {name}: Not available")
        
        if not available_providers:
            print("❌ No LLM providers are available!")
            return False
        
        # Test a simple chat
        test_prompt = "Hello, are you working?"
        messages = [{"role": "user", "content": test_prompt}]
        
        print(f"\n🔍 Testing chat with: '{test_prompt}'")
        
        response = llm_manager.chat(messages)
        
        if response and response.content:
            print(f"✅ LLM Response: {response.content[:100]}...")
            print(f"   Model: {response.model}")
            print(f"   Tokens: {response.tokens_used}")
            return True
        else:
            print("❌ No response from LLM")
            return False
            
    except Exception as e:
        print(f"❌ LLM provider test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_full_orchestrator():
    """Test the full agent orchestrator."""
    print("\n🎯 Testing Full Agent Orchestrator...")
    
    try:
        from services.llm.provider import LLMManager
        from services.agents.langgraph_orchestrator import AgentOrchestrator
        
        # Initialize components
        llm_manager = LLMManager()
        
        # Mock Oracle connection parameters (we won't actually connect)
        orchestrator = AgentOrchestrator(
            llm_provider=llm_manager,
            oracle_dsn="mock://localhost:1521/xe",
            oracle_user="mock_user",
            oracle_password="mock_pass"
        )
        
        print("✅ Agent orchestrator initialized")
        
        # Test the query that failed
        test_query = "tell me about this table in details PIO_ACCOUNTS"
        print(f"\n🔍 Testing query: '{test_query}'")
        
        response = orchestrator.process_query(test_query)
        
        print(f"✅ Response received:")
        print(f"   Answer: {response['answer'][:200]}...")
        print(f"   Confidence: {response['confidence_score']}")
        print(f"   Query Type: {response['query_type']}")
        print(f"   Tools Used: {response['tools_used']}")
        
        if response.get("error"):
            print(f"   ❌ Error: {response['error']}")
            return False
            
        return True
        
    except Exception as e:
        print(f"❌ Full orchestrator test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    print("🚀 Starting AML Agent Debug Tests...")
    print("=" * 50)
    
    # Run tests
    vector_ok = test_vector_retrieval()
    llm_ok = test_llm_provider()
    
    if vector_ok and llm_ok:
        orchestrator_ok = test_full_orchestrator()
    else:
        print("\n❌ Skipping orchestrator test due to component failures")
        orchestrator_ok = False
    
    print("\n" + "=" * 50)
    print("🏁 Test Results Summary:")
    print(f"   Vector Retrieval: {'✅ PASS' if vector_ok else '❌ FAIL'}")
    print(f"   LLM Provider: {'✅ PASS' if llm_ok else '❌ FAIL'}")
    print(f"   Full Orchestrator: {'✅ PASS' if orchestrator_ok else '❌ FAIL'}")
    
    if vector_ok and llm_ok and orchestrator_ok:
        print("\n🎉 All tests passed! The system should be working.")
    else:
        print("\n⚠️  Some tests failed. Check the errors above.")