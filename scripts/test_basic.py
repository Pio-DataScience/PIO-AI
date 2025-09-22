#!/usr/bin/env python3
"""
Simple test to check if PIO-AI core is working.
"""

import sys
import os
from pathlib import Path

# Add package to path
package_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, package_root)

def test_basic_functionality():
    """Test basic functionality step by step."""
    print("🧪 Testing PIO-AI Core Functionality")
    print("=" * 50)
    
    # Test 1: Import basic modules
    print("1. Testing basic imports...")
    try:
        from services.ingest.manifest_reader import read_manifest
        print("   ✅ Manifest reader")
    except Exception as e:
        print(f"   ❌ Manifest reader: {e}")
        return False
    
    # Test 2: Check manifest
    print("2. Testing manifest reading...")
    try:
        manifest = read_manifest()
        projects = manifest.get("projects", [])
        print(f"   ✅ Found {len(projects)} projects")
        for project in projects:
            print(f"      • {project['name']}")
    except Exception as e:
        print(f"   ❌ Manifest reading: {e}")
        return False
    
    # Test 3: Test LLM provider
    print("3. Testing LLM provider...")
    try:
        from services.llm.provider import get_available_providers
        providers = get_available_providers()
        print(f"   ✅ Available providers: {providers}")
    except Exception as e:
        print(f"   ❌ LLM provider: {e}")
        return False
    
    # Test 4: Simple query without indexes
    print("4. Testing simple query...")
    try:
        from services.llm.answer import answer_simple
        if projects:
            project_name = projects[0]['name']
            print(f"   Testing with project: {project_name}")
            
            # This should work even without indexes (using stubs)
            answer = answer_simple("What is this project about?", project_name)
            print(f"   ✅ Got answer: {answer[:100]}...")
        else:
            print("   ⚠️ No projects to test with")
    except Exception as e:
        print(f"   ❌ Simple query: {e}")
        return False
    
    print("\n🎉 All basic tests passed!")
    return True

if __name__ == "__main__":
    success = test_basic_functionality()
    sys.exit(0 if success else 1)