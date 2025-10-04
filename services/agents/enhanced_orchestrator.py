"""
Enhanced LangGraph orchestrator with StateGraph, self-healing nodes, and comprehensive error handling.
Implements production-grade agentic workflow with memory, safety, and observability.
"""

import logging
import uuid
from typing import Dict, List, Optional, Any, Annotated
from datetime import datetime
from dataclasses import dataclass, field

# LangGraph imports
from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.memory import MemorySaver
from typing_extensions import TypedDict

# Import our enhanced components
from .enhanced_memory import EnhancedConversationMemory, create_memory_for_session
from .auto_traversal import AutoTraversalEngine, EntityExtractor, HybridSchemaSearch
from .edge_case_handler import EdgeCaseOrchestrator
from .safety_guards import ComprehensiveSafetyGuards, SafetyLevel
from .schema_overview import SchemaRepository, SchemaOverviewBuilder

logger = logging.getLogger(__name__)


class AgentState(TypedDict):
    """State managed by the agent throughout conversation."""
    # User input
    query: str
    user_id: Optional[str]
    
    # Processing state
    trace_id: str
    session_id: str
    turn_id: str
    timestamp: datetime
    
    # Intent and entities
    intent: Optional[str]
    confidence: float
    entities: List[Dict[str, Any]]
    
    # Context and retrieval
    schema_context: Optional[Dict[str, Any]]
    expanded_context: Optional[Dict[str, Any]]
    relevant_tables: List[str]
    
    # SQL generation
    sql_query: Optional[str]
    sql_safe: bool
    
    # Execution
    query_results: Optional[Any]
    execution_error: Optional[str]
    
    # Answer composition
    final_answer: str
    answer_safe: bool
    
    # Memory and metadata
    conversation_history: List[Dict[str, Any]]
    active_entities: List[str]
    
    # Error handling
    error_count: int
    retry_count: int
    fallback_used: bool


@dataclass
class NodeMetrics:
    """Metrics for node execution."""
    node_name: str
    start_time: datetime
    end_time: Optional[datetime] = None
    duration_ms: Optional[float] = None
    success: bool = True
    error: Optional[str] = None
    
    def complete(self, success: bool = True, error: Optional[str] = None):
        """Mark node as complete."""
        self.end_time = datetime.now()
        self.duration_ms = (self.end_time - self.start_time).total_seconds() * 1000
        self.success = success
        self.error = error


class EnhancedProductionOrchestrator:
    """
    Production-grade orchestrator with StateGraph, self-healing, and comprehensive features.
    """
    
    def __init__(
        self,
        llm_client: Any,
        schema_repo: SchemaRepository,
        safety_guards: Optional[ComprehensiveSafetyGuards] = None,
        edge_case_handler: Optional[EdgeCaseOrchestrator] = None,
        enable_memory: bool = True,
        enable_auto_traversal: bool = True,
        max_retries: int = 2
    ):
        """
        Initialize enhanced orchestrator.
        
        Args:
            llm_client: LLM client for generation
            schema_repo: Schema repository
            safety_guards: Safety validation system
            edge_case_handler: Edge case handling system
            enable_memory: Enable conversation memory
            enable_auto_traversal: Enable automatic query expansion
            max_retries: Maximum retry attempts
        """
        self.llm_client = llm_client
        self.schema_repo = schema_repo
        self.safety_guards = safety_guards or ComprehensiveSafetyGuards()
        self.edge_case_handler = edge_case_handler or EdgeCaseOrchestrator()
        self.enable_memory = enable_memory
        self.enable_auto_traversal = enable_auto_traversal
        self.max_retries = max_retries
        
        # Memory system
        self.memory: Optional[EnhancedConversationMemory] = None
        
        # Auto-traversal system
        if enable_auto_traversal:
            hybrid_search = HybridSchemaSearch(
                vector_retriever=None,  # Initialize with actual components
                graph_client=None
            )
            self.auto_traversal = AutoTraversalEngine(hybrid_search)
        else:
            self.auto_traversal = None
        
        # Schema overview builder
        self.schema_builder = SchemaOverviewBuilder(schema_repo)
        
        # Build state graph
        self.graph = self._build_graph()
        
        # Metrics tracking
        self.node_metrics: List[NodeMetrics] = []
        
        logger.info(
            "Enhanced orchestrator initialized",
            extra={
                "operation": "orchestrator.init",
                "memory_enabled": enable_memory,
                "auto_traversal_enabled": enable_auto_traversal,
                "max_retries": max_retries
            }
        )
    
    def _build_graph(self) -> StateGraph:
        """Build the state graph for agent workflow."""
        # Create state graph
        workflow = StateGraph(AgentState)
        
        # Add nodes
        workflow.add_node("safety_check", self._safety_check_node)
        workflow.add_node("intent_classification", self._intent_classification_node)
        workflow.add_node("auto_traverse", self._auto_traverse_node)
        workflow.add_node("schema_retrieval", self._schema_retrieval_node)
        workflow.add_node("sql_generation", self._sql_generation_node)
        workflow.add_node("sql_validation", self._sql_validation_node)
        workflow.add_node("sql_execution", self._sql_execution_node)
        workflow.add_node("answer_composition", self._answer_composition_node)
        workflow.add_node("answer_review", self._answer_review_node)
        workflow.add_node("error_handler", self._error_handler_node)
        workflow.add_node("self_heal", self._self_heal_node)
        
        # Define edges
        workflow.set_entry_point("safety_check")
        
        # Conditional routing from safety check
        workflow.add_conditional_edges(
            "safety_check",
            self._route_after_safety,
            {
                "proceed": "intent_classification",
                "blocked": END
            }
        )
        
        # Intent classification to auto-traversal or schema retrieval
        workflow.add_conditional_edges(
            "intent_classification",
            self._route_after_intent,
            {
                "auto_traverse": "auto_traverse",
                "schema_only": "schema_retrieval",
                "error": "error_handler"
            }
        )
        
        # Auto-traverse to schema retrieval
        workflow.add_edge("auto_traverse", "schema_retrieval")
        
        # Schema retrieval to SQL generation or direct answer
        workflow.add_conditional_edges(
            "schema_retrieval",
            self._route_after_schema,
            {
                "generate_sql": "sql_generation",
                "direct_answer": "answer_composition",
                "empty": "error_handler"
            }
        )
        
        # SQL generation to validation
        workflow.add_edge("sql_generation", "sql_validation")
        
        # SQL validation routing
        workflow.add_conditional_edges(
            "sql_validation",
            self._route_after_sql_validation,
            {
                "execute": "sql_execution",
                "unsafe": "self_heal",
                "error": "error_handler"
            }
        )
        
        # SQL execution routing
        workflow.add_conditional_edges(
            "sql_execution",
            self._route_after_execution,
            {
                "success": "answer_composition",
                "error": "self_heal"
            }
        )
        
        # Answer composition to review
        workflow.add_edge("answer_composition", "answer_review")
        
        # Answer review to end or self-heal
        workflow.add_conditional_edges(
            "answer_review",
            self._route_after_review,
            {
                "approved": END,
                "sanitize": "self_heal"
            }
        )
        
        # Error handler can retry or end
        workflow.add_conditional_edges(
            "error_handler",
            self._route_after_error,
            {
                "retry": "intent_classification",
                "end": END
            }
        )
        
        # Self-heal can retry SQL or give up
        workflow.add_conditional_edges(
            "self_heal",
            self._route_after_heal,
            {
                "retry_sql": "sql_generation",
                "retry_answer": "answer_composition",
                "give_up": "error_handler"
            }
        )
        
        return workflow.compile()
    
    # Node implementations
    
    def _safety_check_node(self, state: AgentState) -> AgentState:
        """Check query safety."""
        metrics = NodeMetrics("safety_check", datetime.now())
        
        try:
            result = self.safety_guards.check_query(
                state['query'],
                state.get('user_id')
            )
            
            if not result.safe:
                state['final_answer'] = self.edge_case_handler.abuse_detector.get_polite_response()
                state['answer_safe'] = False
                
            metrics.complete(success=result.safe)
            
        except Exception as e:
            logger.error(f"Safety check failed: {e}")
            metrics.complete(success=False, error=str(e))
            state['error_count'] = state.get('error_count', 0) + 1
        
        self.node_metrics.append(metrics)
        return state
    
    def _intent_classification_node(self, state: AgentState) -> AgentState:
        """Classify user intent."""
        metrics = NodeMetrics("intent_classification", datetime.now())
        
        try:
            # Use LLM to classify intent
            prompt = f"""Classify the following query intent:
Query: {state['query']}

Possible intents:
- SCHEMA_QUESTION: Asking about database structure, tables, columns
- DATA_QUERY: Requesting actual data from database
- DOCUMENTATION: Asking for documentation or descriptions
- GENERAL: General question or conversation

Return only the intent name."""
            
            intent = self.llm_client.generate(prompt, max_tokens=50).strip()
            state['intent'] = intent
            state['confidence'] = 0.8  # Would use actual confidence from classifier
            
            # Extract entities
            if self.auto_traversal:
                entities = self.auto_traversal.entity_extractor.extract_entities(state['query'])
                state['entities'] = [
                    {'text': e.text, 'type': e.entity_type, 'confidence': e.confidence}
                    for e in entities
                ]
            
            metrics.complete(success=True)
            
        except Exception as e:
            logger.error(f"Intent classification failed: {e}")
            metrics.complete(success=False, error=str(e))
            state['error_count'] = state.get('error_count', 0) + 1
        
        self.node_metrics.append(metrics)
        return state
    
    def _auto_traverse_node(self, state: AgentState) -> AgentState:
        """Perform automatic query expansion and traversal."""
        metrics = NodeMetrics("auto_traverse", datetime.now())
        
        try:
            if self.auto_traversal:
                # Get conversation context
                is_followup = len(state.get('conversation_history', [])) > 0
                
                # Expand query
                expanded = self.auto_traversal.expand_query(
                    state['query'],
                    is_followup=is_followup
                )
                
                state['expanded_context'] = expanded
                state['relevant_tables'] = [
                    t['name'] for t in expanded.get('relevant_tables', [])
                ]
            
            metrics.complete(success=True)
            
        except Exception as e:
            logger.error(f"Auto-traverse failed: {e}")
            metrics.complete(success=False, error=str(e))
            state['fallback_used'] = True
        
        self.node_metrics.append(metrics)
        return state
    
    def _schema_retrieval_node(self, state: AgentState) -> AgentState:
        """Retrieve relevant schema information."""
        metrics = NodeMetrics("schema_retrieval", datetime.now())
        
        try:
            relevant_tables = state.get('relevant_tables', [])
            
            if not relevant_tables:
                # Fallback: search by query
                results = self.schema_repo.search_tables(state['query'])
                relevant_tables = [t.name for t in results[:5]]
                state['relevant_tables'] = relevant_tables
            
            # Build schema context for LLM
            schema_context = self.schema_builder.build_context_for_query(
                state['query'],
                relevant_tables,
                max_detail_level='medium'
            )
            
            state['schema_context'] = {'text': schema_context, 'tables': relevant_tables}
            
            metrics.complete(success=bool(relevant_tables))
            
        except Exception as e:
            logger.error(f"Schema retrieval failed: {e}")
            metrics.complete(success=False, error=str(e))
            state['error_count'] = state.get('error_count', 0) + 1
        
        self.node_metrics.append(metrics)
        return state
    
    def _sql_generation_node(self, state: AgentState) -> AgentState:
        """Generate SQL query."""
        metrics = NodeMetrics("sql_generation", datetime.now())
        
        try:
            schema_text = state.get('schema_context', {}).get('text', '')
            
            prompt = f"""Generate a SQL query to answer this question:
Question: {state['query']}

Schema information:
{schema_text}

Generate only the SQL query (SELECT statement only):"""
            
            sql = self.llm_client.generate(prompt, max_tokens=500).strip()
            
            # Clean up SQL
            sql = sql.replace('```sql', '').replace('```', '').strip()
            
            state['sql_query'] = sql
            
            metrics.complete(success=True)
            
        except Exception as e:
            logger.error(f"SQL generation failed: {e}")
            metrics.complete(success=False, error=str(e))
            state['execution_error'] = str(e)
        
        self.node_metrics.append(metrics)
        return state
    
    def _sql_validation_node(self, state: AgentState) -> AgentState:
        """Validate SQL for safety."""
        metrics = NodeMetrics("sql_validation", datetime.now())
        
        try:
            sql = state.get('sql_query', '')
            
            if not sql:
                state['sql_safe'] = False
                metrics.complete(success=False, error="No SQL generated")
            else:
                result = self.safety_guards.validate_sql(sql)
                state['sql_safe'] = result.safe
                
                if not result.safe:
                    state['execution_error'] = result.reason
                
                metrics.complete(success=result.safe)
        
        except Exception as e:
            logger.error(f"SQL validation failed: {e}")
            metrics.complete(success=False, error=str(e))
            state['sql_safe'] = False
        
        self.node_metrics.append(metrics)
        return state
    
    def _sql_execution_node(self, state: AgentState) -> AgentState:
        """Execute SQL query (placeholder - integrate with actual DB executor)."""
        metrics = NodeMetrics("sql_execution", datetime.now())
        
        try:
            # Placeholder: In production, use actual SQL executor
            state['query_results'] = {"message": "SQL execution would happen here"}
            metrics.complete(success=True)
            
        except Exception as e:
            logger.error(f"SQL execution failed: {e}")
            metrics.complete(success=False, error=str(e))
            state['execution_error'] = str(e)
        
        self.node_metrics.append(metrics)
        return state
    
    def _answer_composition_node(self, state: AgentState) -> AgentState:
        """Compose final answer."""
        metrics = NodeMetrics("answer_composition", datetime.now())
        
        try:
            schema_context = state.get('schema_context', {}).get('text', '')
            results = state.get('query_results')
            
            prompt = f"""Answer the user's question based on this information:

Question: {state['query']}

Schema context:
{schema_context}

Query results:
{results}

Provide a clear, helpful answer:"""
            
            answer = self.llm_client.generate(prompt, max_tokens=500)
            state['final_answer'] = answer.strip()
            
            metrics.complete(success=True)
            
        except Exception as e:
            logger.error(f"Answer composition failed: {e}")
            metrics.complete(success=False, error=str(e))
            state['final_answer'] = "I apologize, but I encountered an error composing the answer."
        
        self.node_metrics.append(metrics)
        return state
    
    def _answer_review_node(self, state: AgentState) -> AgentState:
        """Review answer for safety and compliance."""
        metrics = NodeMetrics("answer_review", datetime.now())
        
        try:
            answer = state.get('final_answer', '')
            
            result = self.safety_guards.review_answer(answer)
            state['answer_safe'] = result.safe
            
            if result.sanitized_content:
                state['final_answer'] = result.sanitized_content
            
            metrics.complete(success=True)
            
        except Exception as e:
            logger.error(f"Answer review failed: {e}")
            metrics.complete(success=False, error=str(e))
            state['answer_safe'] = True  # Default to true on error
        
        self.node_metrics.append(metrics)
        return state
    
    def _error_handler_node(self, state: AgentState) -> AgentState:
        """Handle errors with fallback strategies."""
        metrics = NodeMetrics("error_handler", datetime.now())
        
        try:
            error = state.get('execution_error', 'Unknown error')
            
            # Use edge case handler
            result = self.edge_case_handler.handle(
                "empty_results",
                query=state['query'],
                search_type="schema"
            )
            
            state['final_answer'] = result.response
            state['fallback_used'] = True
            
            metrics.complete(success=True)
            
        except Exception as e:
            logger.error(f"Error handler failed: {e}")
            metrics.complete(success=False, error=str(e))
            state['final_answer'] = "I apologize, but I encountered an unexpected error."
        
        self.node_metrics.append(metrics)
        return state
    
    def _self_heal_node(self, state: AgentState) -> AgentState:
        """Attempt to self-heal from errors."""
        metrics = NodeMetrics("self_heal", datetime.now())
        
        try:
            retry_count = state.get('retry_count', 0)
            
            if retry_count < self.max_retries:
                state['retry_count'] = retry_count + 1
                logger.info(f"Self-healing attempt {retry_count + 1}")
                metrics.complete(success=True)
            else:
                logger.warning("Max retries exceeded")
                metrics.complete(success=False, error="Max retries exceeded")
        
        except Exception as e:
            logger.error(f"Self-heal failed: {e}")
            metrics.complete(success=False, error=str(e))
        
        self.node_metrics.append(metrics)
        return state
    
    # Routing functions
    
    def _route_after_safety(self, state: AgentState) -> str:
        """Route after safety check."""
        return "blocked" if not state.get('answer_safe', True) else "proceed"
    
    def _route_after_intent(self, state: AgentState) -> str:
        """Route after intent classification."""
        intent = state.get('intent', '')
        
        if state.get('error_count', 0) > 0:
            return "error"
        
        if intent == 'DATA_QUERY' and self.enable_auto_traversal:
            return "auto_traverse"
        
        return "schema_only"
    
    def _route_after_schema(self, state: AgentState) -> str:
        """Route after schema retrieval."""
        if not state.get('relevant_tables'):
            return "empty"
        
        if state.get('intent') == 'DATA_QUERY':
            return "generate_sql"
        
        return "direct_answer"
    
    def _route_after_sql_validation(self, state: AgentState) -> str:
        """Route after SQL validation."""
        if state.get('error_count', 0) > 0:
            return "error"
        
        return "execute" if state.get('sql_safe', False) else "unsafe"
    
    def _route_after_execution(self, state: AgentState) -> str:
        """Route after SQL execution."""
        return "success" if not state.get('execution_error') else "error"
    
    def _route_after_review(self, state: AgentState) -> str:
        """Route after answer review."""
        return "approved" if state.get('answer_safe', True) else "sanitize"
    
    def _route_after_error(self, state: AgentState) -> str:
        """Route after error handling."""
        retry_count = state.get('retry_count', 0)
        return "retry" if retry_count < self.max_retries else "end"
    
    def _route_after_heal(self, state: AgentState) -> str:
        """Route after self-heal."""
        retry_count = state.get('retry_count', 0)
        
        if retry_count >= self.max_retries:
            return "give_up"
        
        # Determine what to retry
        if not state.get('sql_safe', True):
            return "retry_sql"
        
        return "retry_answer"
    
    def process_query(
        self,
        query: str,
        session_id: Optional[str] = None,
        user_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Process a user query through the orchestrator.
        
        Args:
            query: User query
            session_id: Session identifier
            user_id: User identifier
            
        Returns:
            Processing result with answer and metadata
        """
        # Initialize state
        initial_state: AgentState = {
            'query': query,
            'user_id': user_id,
            'trace_id': str(uuid.uuid4()),
            'session_id': session_id or str(uuid.uuid4()),
            'turn_id': str(uuid.uuid4()),
            'timestamp': datetime.now(),
            'intent': None,
            'confidence': 0.0,
            'entities': [],
            'schema_context': None,
            'expanded_context': None,
            'relevant_tables': [],
            'sql_query': None,
            'sql_safe': False,
            'query_results': None,
            'execution_error': None,
            'final_answer': '',
            'answer_safe': True,
            'conversation_history': [],
            'active_entities': [],
            'error_count': 0,
            'retry_count': 0,
            'fallback_used': False
        }
        
        # Run through graph
        logger.info(
            f"Processing query: {query[:100]}",
            extra={
                "operation": "orchestrator.process_query",
                "trace_id": initial_state['trace_id'],
                "session_id": initial_state['session_id']
            }
        )
        
        try:
            final_state = self.graph.invoke(initial_state)
            
            # Save to memory if enabled
            if self.enable_memory and self.memory:
                self.memory.add_turn(
                    user_query=query,
                    agent_response=final_state['final_answer'],
                    intent=final_state.get('intent'),
                    entities=[e['text'] for e in final_state.get('entities', [])],
                    tools_used=['sql'] if final_state.get('sql_query') else [],
                    trace_id=final_state['trace_id']
                )
            
            # Compile metrics
            metrics_summary = {
                'total_nodes': len(self.node_metrics),
                'total_duration_ms': sum(m.duration_ms for m in self.node_metrics if m.duration_ms),
                'failures': sum(1 for m in self.node_metrics if not m.success),
                'by_node': {m.node_name: m.duration_ms for m in self.node_metrics}
            }
            
            return {
                'answer': final_state['final_answer'],
                'trace_id': final_state['trace_id'],
                'intent': final_state.get('intent'),
                'sql_used': final_state.get('sql_query'),
                'fallback_used': final_state.get('fallback_used', False),
                'metrics': metrics_summary
            }
            
        except Exception as e:
            logger.error(f"Orchestrator failed: {e}", exc_info=True)
            return {
                'answer': "I apologize, but I encountered an unexpected error processing your request.",
                'error': str(e),
                'trace_id': initial_state['trace_id']
            }
