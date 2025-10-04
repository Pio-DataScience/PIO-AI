"""
Test script for query reformulation and conversation context.
Validates that the intelligent reformulator properly handles queries and maintains context.
"""

import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from services.agents.query_reformulator import (
    IntelligentQueryReformulator,
    QueryIntent
)


def test_basic_reformulation():
    """Test basic query reformulation."""
    print("=" * 80)
    print("TEST 1: Basic Query Reformulation")
    print("=" * 80)
    
    reformulator = IntelligentQueryReformulator()
    
    test_cases = [
        "what is PIO_ACCOUNTS table about?",
        "list all columns in PIO_ACCOUNTS",
        "what is ACCOUNT_NUMBER column?",
        "show me the purpose of this table",
        "what tables are related?"
    ]
    
    for query in test_cases:
        rq = reformulator.reformulate(query)
        print(f"\nOriginal:     '{query}'")
        print(f"Reformulated: '{rq.reformulated_query}'")
        print(f"Intent:       {rq.intent.value}")
        print(f"Target Table: {rq.target_table}")
        print(f"Complete MD:  {rq.should_retrieve_complete_metadata}")
        print(f"Confidence:   {rq.confidence:.2f}")


def test_follow_up_context():
    """Test conversation context and follow-up detection."""
    print("\n" + "=" * 80)
    print("TEST 2: Follow-Up Context Tracking")
    print("=" * 80)
    
    reformulator = IntelligentQueryReformulator()
    session_id = "test_session_123"
    
    # Turn 1: Initial query about PIO_ACCOUNTS
    query1 = "what is PIO_ACCOUNTS table about?"
    rq1 = reformulator.reformulate(query1, session_id)
    
    print("\n--- Turn 1 ---")
    print(f"Query:        '{query1}'")
    print(f"Reformulated: '{rq1.reformulated_query}'")
    print(f"Intent:       {rq1.intent.value}")
    print(f"Target Table: {rq1.target_table}")
    print(f"Is Follow-up: False")
    
    # Check context state
    context = reformulator.get_context_summary()
    print(f"\nContext State:")
    print(f"  Last Table:  {context['last_table']}")
    print(f"  Last Intent: {context['last_intent']}")
    print(f"  Turn Count:  {context['turn_count']}")
    
    # Turn 2: Follow-up question
    query2 = "no I'm sure there is more check"
    rq2 = reformulator.reformulate(query2, session_id)
    
    print("\n--- Turn 2 (Follow-up) ---")
    print(f"Query:        '{query2}'")
    print(f"Reformulated: '{rq2.reformulated_query}'")
    print(f"Intent:       {rq2.intent.value}")
    print(f"Target Table: {rq2.target_table}")
    print(f"Is Follow-up: {reformulator.context.is_follow_up(query2)}")
    
    # Validate that context was used
    context2 = reformulator.get_context_summary()
    print(f"\nContext State After Turn 2:")
    print(f"  Last Table:  {context2['last_table']}")
    print(f"  Turn Count:  {context2['turn_count']}")
    
    # Verify table continuity
    assert rq2.target_table == "PIO_ACCOUNTS", "Follow-up should use context table!"
    print("\n✅ PASS: Follow-up correctly used context table (PIO_ACCOUNTS)")
    
    # Turn 3: Another follow-up
    query3 = "show me those columns"
    rq3 = reformulator.reformulate(query3, session_id)
    
    print("\n--- Turn 3 (Another Follow-up) ---")
    print(f"Query:        '{query3}'")
    print(f"Reformulated: '{rq3.reformulated_query}'")
    print(f"Target Table: {rq3.target_table}")
    print(f"Is Follow-up: {reformulator.context.is_follow_up(query3)}")
    
    assert rq3.target_table == "PIO_ACCOUNTS", "Second follow-up should still use context!"
    print("✅ PASS: Second follow-up maintained context")


def test_intent_detection():
    """Test intent detection for different query types."""
    print("\n" + "=" * 80)
    print("TEST 3: Intent Detection")
    print("=" * 80)
    
    reformulator = IntelligentQueryReformulator()
    
    test_cases = [
        ("what is PIO_ACCOUNTS about?", QueryIntent.TABLE_METADATA),
        ("list all columns", QueryIntent.COLUMN_LIST),
        ("show me all columns in this table", QueryIntent.COLUMN_LIST),
        ("what is ACCOUNT_NUMBER column?", QueryIntent.COLUMN_DETAILS),
        ("what is the purpose of PIO_ACCOUNTS?", QueryIntent.TABLE_PURPOSE),
        ("what tables are related to PIO_ACCOUNTS?", QueryIntent.TABLE_RELATIONSHIPS),
    ]
    
    passed = 0
    failed = 0
    
    for query, expected_intent in test_cases:
        rq = reformulator.reformulate(query)
        status = "✅" if rq.intent == expected_intent else "❌"
        
        print(f"\n{status} Query: '{query}'")
        print(f"   Expected: {expected_intent.value}")
        print(f"   Got:      {rq.intent.value}")
        
        if rq.intent == expected_intent:
            passed += 1
        else:
            failed += 1
    
    print(f"\n{'='*80}")
    print(f"Results: {passed} passed, {failed} failed")
    
    if failed == 0:
        print("✅ ALL INTENT DETECTION TESTS PASSED")
    else:
        print(f"⚠️ {failed} tests failed")


def test_complete_metadata_detection():
    """Test detection of when complete metadata is needed."""
    print("\n" + "=" * 80)
    print("TEST 4: Complete Metadata Detection")
    print("=" * 80)
    
    reformulator = IntelligentQueryReformulator()
    
    # These should need complete metadata
    complete_metadata_queries = [
        "what is PIO_ACCOUNTS about?",
        "describe PIO_ACCOUNTS table",
        "list all columns in PIO_ACCOUNTS",
        "show me complete structure of PIO_ACCOUNTS",
        "how many columns does PIO_ACCOUNTS have?",
    ]
    
    print("\nQueries that SHOULD retrieve complete metadata:")
    for query in complete_metadata_queries:
        rq = reformulator.reformulate(query)
        status = "✅" if rq.should_retrieve_complete_metadata else "❌"
        print(f"{status} '{query}' -> Complete: {rq.should_retrieve_complete_metadata}")
    
    # These should NOT need complete metadata
    partial_queries = [
        "what is ACCOUNT_NUMBER?",
        "show me transactions",
    ]
    
    print("\nQueries that should NOT need complete metadata:")
    for query in partial_queries:
        rq = reformulator.reformulate(query)
        status = "✅" if not rq.should_retrieve_complete_metadata else "❌"
        print(f"{status} '{query}' -> Complete: {rq.should_retrieve_complete_metadata}")


def test_table_extraction():
    """Test table name extraction from queries."""
    print("\n" + "=" * 80)
    print("TEST 5: Table Name Extraction")
    print("=" * 80)
    
    reformulator = IntelligentQueryReformulator()
    
    test_cases = [
        ("what is PIO_ACCOUNTS about?", "PIO_ACCOUNTS"),
        ("tell me about the PIO_ACCOUNTS table", "PIO_ACCOUNTS"),
        ("show me CUSTOMER_DATA", "CUSTOMER_DATA"),
        ("PIO_TRANSACTIONS analysis", "PIO_TRANSACTIONS"),
        ("what about pio_accounts?", "PIO_ACCOUNTS"),  # Case insensitive
    ]
    
    for query, expected_table in test_cases:
        rq = reformulator.reformulate(query)
        status = "✅" if rq.target_table == expected_table else "❌"
        
        print(f"\n{status} Query: '{query}'")
        print(f"   Expected: {expected_table}")
        print(f"   Got:      {rq.target_table}")


def test_context_reset():
    """Test context reset functionality."""
    print("\n" + "=" * 80)
    print("TEST 6: Context Reset")
    print("=" * 80)
    
    reformulator = IntelligentQueryReformulator()
    
    # Build up context
    rq1 = reformulator.reformulate("what is PIO_ACCOUNTS about?")
    context_before = reformulator.get_context_summary()
    
    print(f"Context before reset:")
    print(f"  Last Table: {context_before['last_table']}")
    print(f"  Turn Count: {context_before['turn_count']}")
    
    # Reset
    reformulator.reset_context()
    context_after = reformulator.get_context_summary()
    
    print(f"\nContext after reset:")
    print(f"  Last Table: {context_after['last_table']}")
    print(f"  Turn Count: {context_after['turn_count']}")
    
    assert context_after['last_table'] is None, "Context should be cleared"
    assert context_after['turn_count'] == 0, "Turn count should reset"
    print("\n✅ PASS: Context reset successful")


def run_all_tests():
    """Run all test suites."""
    print("\n" + "=" * 80)
    print("INTELLIGENT QUERY REFORMULATOR TEST SUITE")
    print("=" * 80)
    
    try:
        test_basic_reformulation()
        test_follow_up_context()
        test_intent_detection()
        test_complete_metadata_detection()
        test_table_extraction()
        test_context_reset()
        
        print("\n" + "=" * 80)
        print("✅ ALL TEST SUITES COMPLETED")
        print("=" * 80)
        
    except Exception as e:
        print("\n" + "=" * 80)
        print(f"❌ TEST FAILED WITH ERROR: {e}")
        print("=" * 80)
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    run_all_tests()
