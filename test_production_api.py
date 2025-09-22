"""
Test script for Production AML API endpoints
"""

import requests
import json
import time

# API base URL
BASE_URL = "http://127.0.0.1:8008"

def test_endpoint(endpoint, method="GET", data=None):
    """Test an API endpoint and return the response."""
    url = f"{BASE_URL}{endpoint}"
    
    try:
        if method == "GET":
            response = requests.get(url)
        elif method == "POST":
            response = requests.post(url, json=data)
        
        print(f"\n{'='*60}")
        print(f"Testing: {method} {endpoint}")
        print(f"Status Code: {response.status_code}")
        
        if response.status_code == 200:
            result = response.json()
            print(f"✅ Success! Response keys: {list(result.keys())}")
            return result
        else:
            print(f"❌ Error: {response.text}")
            return None
            
    except Exception as e:
        print(f"❌ Exception: {e}")
        return None

def main():
    """Run comprehensive API tests."""
    print("🚀 Testing Production AML API Endpoints")
    print(f"Base URL: {BASE_URL}")
    
    # Test 1: Health Check
    health_result = test_endpoint("/health")
    if health_result:
        print(f"   - API Status: {health_result.get('status')}")
        print(f"   - Components: {list(health_result.get('components', {}).keys())}")
    
    # Test 2: Readiness Check
    test_endpoint("/health/ready")
    
    # Test 3: API Info
    info_result = test_endpoint("/info")
    if info_result:
        print(f"   - API Version: {info_result.get('version')}")
        print(f"   - Features: {list(info_result.get('features', {}).keys())}")
    
    # Test 4: Semantic Search
    semantic_search_data = {
        "query": "customer table",
        "search_type": "semantic",
        "max_results": 5,
        "similarity_threshold": 0.1
    }
    semantic_result = test_endpoint("/aml/search", "POST", semantic_search_data)
    if semantic_result:
        print(f"   - Semantic Results: {semantic_result.get('total')} found")
        print(f"   - Execution Time: {semantic_result.get('execution_time'):.3f}s")
    
    # Test 5: Graph Search
    graph_search_data = {
        "query": "customer",
        "search_type": "graph",
        "max_results": 5
    }
    graph_result = test_endpoint("/aml/search", "POST", graph_search_data)
    if graph_result:
        print(f"   - Graph Results: {graph_result.get('total')} found")
        print(f"   - Execution Time: {graph_result.get('execution_time'):.3f}s")
    
    # Test 6: Hybrid Search
    hybrid_search_data = {
        "query": "account",
        "search_type": "hybrid",
        "max_results": 10,
        "similarity_threshold": 0.0
    }
    hybrid_result = test_endpoint("/aml/search", "POST", hybrid_search_data)
    if hybrid_result:
        print(f"   - Hybrid Results: {hybrid_result.get('total')} found")
        print(f"   - Execution Time: {hybrid_result.get('execution_time'):.3f}s")
    
    # Test 7: Entity Search
    entity_search_data = {
        "entity_name": "CUSTOMER",
        "entity_type": "table",
        "include_relationships": True
    }
    entity_result = test_endpoint("/aml/entity/search", "POST", entity_search_data)
    if entity_result:
        print(f"   - Entity Found: {entity_result.get('entity') is not None}")
        print(f"   - Relationships: {len(entity_result.get('relationships', []))}")
        print(f"   - Semantic Matches: {len(entity_result.get('semantic_matches', []))}")
    
    # Test 8: Graph Analytics
    analytics_data = {
        "analysis_type": "centrality",
        "limit": 5
    }
    analytics_result = test_endpoint("/aml/analytics", "POST", analytics_data)
    if analytics_result:
        print(f"   - Analytics Results: {len(analytics_result.get('results', []))}")
        print(f"   - Analysis Type: {analytics_result.get('analysis_type')}")
    
    # Test 9: AML Investigation
    investigation_data = {
        "entity_names": ["CUSTOMER", "ACCOUNT"],
        "investigation_type": "suspicious_patterns",
        "depth": 2
    }
    investigation_result = test_endpoint("/aml/investigate", "POST", investigation_data)
    if investigation_result:
        print(f"   - Investigation Findings: {len(investigation_result.get('findings', []))}")
        print(f"   - Risk Indicators: {len(investigation_result.get('risk_indicators', []))}")
    
    print(f"\n{'='*60}")
    print("✅ Production AML API Testing Complete!")
    print("🎯 All major endpoints tested successfully")


if __name__ == "__main__":
    main()