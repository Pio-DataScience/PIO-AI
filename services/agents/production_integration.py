"""
Integration example showing how to use all enhanced components together.
This demonstrates the complete production-grade agentic database assistant.
"""

from pathlib import Path
from typing import Optional
import logging

# Import all enhanced components
from services.agents.enhanced_memory import EnhancedConversationMemory, create_memory_for_session
from services.agents.auto_traversal import AutoTraversalEngine, EntityExtractor, HybridSchemaSearch
from services.agents.edge_case_handler import EdgeCaseOrchestrator
from services.agents.safety_guards import ComprehensiveSafetyGuards
from services.agents.schema_overview import SchemaRepository, SchemaOverviewBuilder
from services.agents.enhanced_orchestrator import EnhancedProductionOrchestrator
from services.agents.enhanced_observability import configure_observability, get_observability


class ProductionAgenticAssistant:
    """
    Complete production-grade agentic database assistant.
    Integrates all enhanced components for a robust, scalable system.
    """
    
    def __init__(
        self,
        llm_client,
        catalog_db_path: Path,
        vector_retriever=None,
        bm25_retriever=None,
        graph_client=None,
        enable_memory: bool = True,
        enable_auto_traversal: bool = True,
        log_level: str = "INFO"
    ):
        """
        Initialize production assistant.
        
        Args:
            llm_client: LLM client for generation
            catalog_db_path: Path to catalog database
            vector_retriever: Optional vector search
            bm25_retriever: Optional BM25 search
            graph_client: Optional Neo4j client
            enable_memory: Enable conversation memory
            enable_auto_traversal: Enable auto-traversal
            log_level: Logging level
        """
        # Configure observability first
        self.observability = configure_observability(
            log_level=log_level,
            log_file=Path("logs/production_agent.log"),
            enable_console=True,
            enable_json=True
        )
        
        self.logger = logging.getLogger(__name__)
        
        # Initialize schema repository with caching
        self.schema_repo = SchemaRepository(
            catalog_db_path=catalog_db_path,
            graph_client=graph_client,
            cache_ttl=300  # 5 minutes
        )
        
        # Initialize safety guards
        self.safety_guards = ComprehensiveSafetyGuards()
        
        # Initialize edge case handler
        self.edge_case_handler = EdgeCaseOrchestrator()
        
        # Initialize hybrid search for auto-traversal
        self.hybrid_search = None
        if enable_auto_traversal:
            self.hybrid_search = HybridSchemaSearch(
                bm25_retriever=bm25_retriever,
                vector_retriever=vector_retriever,
                graph_client=graph_client,
                catalog_db_path=catalog_db_path
            )
        
        # Initialize orchestrator
        self.orchestrator = EnhancedProductionOrchestrator(
            llm_client=llm_client,
            schema_repo=self.schema_repo,
            safety_guards=self.safety_guards,
            edge_case_handler=self.edge_case_handler,
            enable_memory=enable_memory,
            enable_auto_traversal=enable_auto_traversal,
            max_retries=2
        )
        
        self.logger.info(
            "Production assistant initialized",
            extra={
                "operation": "assistant.init",
                "memory_enabled": enable_memory,
                "auto_traversal_enabled": enable_auto_traversal
            }
        )
    
    def chat(
        self,
        query: str,
        session_id: Optional[str] = None,
        user_id: Optional[str] = None
    ) -> dict:
        """
        Process a user query with full tracing and observability.
        
        Args:
            query: User query
            session_id: Optional session ID
            user_id: Optional user ID
            
        Returns:
            Response dictionary with answer and metadata
        """
        # Start trace
        trace = self.observability.start_trace(
            session_id=session_id,
            user_id=user_id
        )
        
        try:
            # Log incoming query
            self.observability.log_event(
                event_type="query.received",
                message=f"Processing query: {query[:100]}",
                level="INFO",
                trace_id=trace.trace_id,
                session_id=session_id,
                user_id=user_id,
                query_length=len(query)
            )
            
            # Process through orchestrator
            with self.observability.trace_operation(
                "orchestrator.process",
                trace_context=trace,
                metadata={"query": query[:100]}
            ):
                result = self.orchestrator.process_query(
                    query=query,
                    session_id=session_id,
                    user_id=user_id
                )
            
            # Log response
            self.observability.log_event(
                event_type="query.completed",
                message="Query processed successfully",
                level="INFO",
                trace_id=trace.trace_id,
                session_id=session_id,
                user_id=user_id,
                answer_length=len(result.get('answer', '')),
                fallback_used=result.get('fallback_used', False)
            )
            
            # Add trace info to result
            result['trace_summary'] = self.observability.end_trace(trace.trace_id)
            
            return result
            
        except Exception as e:
            self.logger.error(
                f"Query processing failed: {e}",
                extra={
                    "operation": "assistant.chat",
                    "trace_id": trace.trace_id,
                    "error": str(e)
                },
                exc_info=True
            )
            
            self.observability.end_trace(trace.trace_id)
            
            return {
                'answer': "I apologize, but I encountered an unexpected error.",
                'error': str(e),
                'trace_id': trace.trace_id
            }
    
    def get_schema_overview(self) -> str:
        """
        Get high-level schema overview.
        
        Returns:
            Formatted schema summary
        """
        return self.schema_repo.get_schema_summary()
    
    def get_table_info(self, table_name: str) -> str:
        """
        Get detailed information about a specific table.
        
        Args:
            table_name: Name of table
            
        Returns:
            Formatted table information
        """
        return self.schema_repo.get_table_detail_for_llm(table_name)
    
    def export_metrics(self, output_path: Path):
        """
        Export performance metrics.
        
        Args:
            output_path: Output file path
        """
        self.observability.export_metrics(output_path)
    
    def get_cache_stats(self) -> dict:
        """
        Get cache statistics.
        
        Returns:
            Cache statistics
        """
        return self.schema_repo.get_cache_stats()


# Example usage
def main():
    """Example of using the production assistant."""
    
    # Mock LLM client (replace with actual implementation)
    class MockLLM:
        def generate(self, prompt: str, max_tokens: int = 500) -> str:
            return "Mock response"
    
    # Initialize assistant
    assistant = ProductionAgenticAssistant(
        llm_client=MockLLM(),
        catalog_db_path=Path("warehouse/catalog.db"),
        enable_memory=True,
        enable_auto_traversal=True,
        log_level="INFO"
    )
    
    # Example conversation
    session_id = "test-session-001"
    user_id = "user-123"
    
    # Query 1: Schema question
    print("\\n=== Query 1: Schema Question ===")
    result1 = assistant.chat(
        query="What tables contain customer information?",
        session_id=session_id,
        user_id=user_id
    )
    print(f"Answer: {result1['answer']}")
    print(f"Intent: {result1.get('intent')}")
    print(f"Trace ID: {result1.get('trace_id')}")
    
    # Query 2: Data question
    print("\\n=== Query 2: Data Question ===")
    result2 = assistant.chat(
        query="Show me the high-risk customers",
        session_id=session_id,
        user_id=user_id
    )
    print(f"Answer: {result2['answer']}")
    print(f"SQL Used: {result2.get('sql_used')}")
    print(f"Fallback: {result2.get('fallback_used')}")
    
    # Query 3: Follow-up question
    print("\\n=== Query 3: Follow-up ===")
    result3 = assistant.chat(
        query="What columns are available in those tables?",
        session_id=session_id,
        user_id=user_id
    )
    print(f"Answer: {result3['answer']}")
    
    # Get metrics
    print("\\n=== Performance Metrics ===")
    metrics = assistant.observability.get_metrics_summary()
    print(f"Total operations: {sum(op['count'] for op in metrics['operations'].values())}")
    print(f"Total errors: {metrics['total_errors']}")
    
    # Export metrics
    assistant.export_metrics(Path("data/observability/metrics.json"))
    
    # Get cache stats
    print("\\n=== Cache Statistics ===")
    cache_stats = assistant.get_cache_stats()
    print(f"Cache size: {cache_stats['size']}/{cache_stats['max_size']}")
    print(f"Hit rate: {cache_stats['hit_rate']:.2%}")
    
    print("\\n=== Demo Complete ===")


if __name__ == "__main__":
    main()
