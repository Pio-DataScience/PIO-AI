"""
Modern Agentic Assistant using LangGraph - Industry Standard Implementation.
Follows plan → act → observe → re-plan pattern with comprehensive observability.
"""

import uuid
import json
import time
from datetime import datetime
from typing import Dict, Any, List, Optional, TypedDict, Literal
from pathlib import Path

from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver

from .modern_agentic_router import (
    ModernAgenticRouter, IntentType, IntentClassification, 
    ConversationMemory, ConversationTurn, SafetyGuards
)
from .observability import get_observability, traced_operation, log_performance
from .schema_retriever import SchemaRetriever
from .sql_generator import SQLGenerator
from .sql_executor import SQLExecutor
from .answer_composer import AnswerComposer
from ..llm.provider import LLMProvider

logger, tracer = get_observability()


class AgentState(TypedDict):
    """Rich state for modern agentic workflow."""
    # Core conversation
    session_id: str
    turn_id: str
    query: str
    response: str
    
    # Intent and routing
    intent_classification: Optional[IntentClassification]
    needs_tools: bool
    route_decision: str
    
    # Context and memory
    conversation_context: Dict[str, Any]
    entities: Dict[str, List[str]]
    context_carryover: List[str]
    
    # Tool workflow
    schema_retrieved: Optional[Dict[str, Any]]
    sql_generated: Optional[str]
    sql_validated: Optional[Dict[str, Any]]
    sql_results: Optional[List[Dict[str, Any]]]
    final_answer: Optional[str]
    
    # Execution control
    retry_count: int
    max_retries: int
    errors: List[str]
    confidence_score: float
    
    # Observability
    trace_id: str
    execution_path: List[str]
    tool_calls: List[Dict[str, Any]]
    performance_metrics: Dict[str, float]


class ModernAgentOrchestrator:
    """
    Production-grade agentic assistant following industry patterns:
    - LLM-first conversation with tool-awareness
    - Graph-based orchestration with retries and self-healing
    - Comprehensive observability and safety
    """
    
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        
        # Initialize LLM manager instead of abstract provider
        from services.llm.provider import LLMManager
        self.llm_manager = LLMManager()
        
        # Set the preferred provider if specified
        llm_config = config.get("llm", {})
        if "provider" in llm_config:
            self.llm_manager.set_default_provider(llm_config["provider"])
        
        # Initialize components
        self.router = ModernAgenticRouter(self.llm_manager)
        self.memory = ConversationMemory(Path(config.get("memory_path", "memory")))
        self.safety = SafetyGuards()
        
        # Initialize tools
        self.schema_retriever = SchemaRetriever(config.get("schema_db_path"))
        self.sql_generator = SQLGenerator(self.llm_manager)
        self.sql_executor = SQLExecutor(config.get("db_config", {}))
        self.answer_composer = AnswerComposer(self.llm_manager)
        
        # Build the graph
        self.graph = self._build_graph()
        
        logger.log_operation(
            component="orchestrator",
            operation="initialize",
            phase="complete",
            outcome="success",
            config_keys=list(config.keys())
        )
    
    def _build_graph(self) -> StateGraph:
        """Build the state graph following industry standard patterns."""
        
        # Create the graph
        workflow = StateGraph(AgentState)
        
        # Add nodes following plan → act → observe → re-plan pattern
        workflow.add_node("route", self._route_node)
        workflow.add_node("conversation", self._conversation_node) 
        workflow.add_node("schema_retrieve", self._schema_retrieve_node)
        workflow.add_node("sql_generate", self._sql_generate_node)
        workflow.add_node("sql_validate", self._sql_validate_node)
        workflow.add_node("sql_execute", self._sql_execute_node)
        workflow.add_node("compose_answer", self._compose_answer_node)
        workflow.add_node("save_memory", self._save_memory_node)
        workflow.add_node("handle_error", self._handle_error_node)
        workflow.add_node("self_heal", self._self_heal_node)
        
        # Set entry point
        workflow.set_entry_point("route")
        
        # Add routing logic
        workflow.add_conditional_edges(
            "route",
            self._route_decision,
            {
                "conversation": "conversation",
                "schema_task": "schema_retrieve", 
                "data_task": "schema_retrieve",
                "follow_up": "schema_retrieve",
                "abuse": "conversation",
                "error": "handle_error"
            }
        )
        
        # Conversation path
        workflow.add_edge("conversation", "save_memory")
        
        # Data workflow with vector-only LLM responses (no SQL generation)
        workflow.add_conditional_edges(
            "schema_retrieve",
            self._check_retrieval_success,
            {
                "success": "compose_answer",  # Direct to LLM response
                "empty_retry": "self_heal",
                "error": "handle_error"
            }
        )
        
        workflow.add_conditional_edges(
            "sql_generate", 
            self._check_generation_success,
            {
                "success": "sql_validate",
                "retry": "self_heal", 
                "error": "handle_error"
            }
        )
        
        workflow.add_conditional_edges(
            "sql_validate",
            self._check_validation_success, 
            {
                "safe": "sql_execute",
                "unsafe": "handle_error",
                "retry": "self_heal"
            }
        )
        
        workflow.add_conditional_edges(
            "sql_execute",
            self._check_execution_success,
            {
                "success": "compose_answer",
                "retry": "self_heal",
                "error": "handle_error" 
            }
        )
        
        workflow.add_edge("compose_answer", "save_memory")
        workflow.add_edge("save_memory", END)
        workflow.add_edge("handle_error", "save_memory")
        
        # Self-healing loops back to appropriate node
        workflow.add_conditional_edges(
            "self_heal",
            self._self_heal_decision,
            {
                "retry_schema": "schema_retrieve",
                "retry_sql": "sql_generate", 
                "retry_execute": "sql_execute",
                "give_up": "handle_error"
            }
        )
        
        # Compile with memory
        checkpointer = MemorySaver()
        return workflow.compile(checkpointer=checkpointer)
    
    @traced_operation("process_query", component="orchestrator")
    async def process_query(self, query: str, session_id: str) -> Dict[str, Any]:
        """
        Main entry point for processing user queries.
        Follows industry standard patterns for conversation and tool orchestration.
        """
        
        # Set up observability context
        trace_id = str(uuid.uuid4())
        turn_id = str(uuid.uuid4())
        logger.set_trace_context(trace_id, session_id)
        
        start_time = time.time()
        
        try:
            # Get conversation context
            conversation_context = self.memory.get_context(session_id)
            
            # Initialize state
            initial_state = {
                "session_id": session_id,
                "turn_id": turn_id,
                "query": query,
                "response": "",
                "intent_classification": None,
                "needs_tools": False,
                "route_decision": "",
                "conversation_context": conversation_context,
                "entities": {},
                "context_carryover": [],
                "schema_retrieved": None,
                "sql_generated": None,
                "sql_validated": None,
                "sql_results": None,
                "final_answer": None,
                "retry_count": 0,
                "max_retries": 3,
                "errors": [],
                "confidence_score": 0.0,
                "trace_id": trace_id,
                "execution_path": [],
                "tool_calls": [],
                "performance_metrics": {}
            }
            
            # Execute the graph
            config = {"configurable": {"thread_id": session_id}}
            final_state = await self.graph.ainvoke(initial_state, config)
            
            # Calculate metrics
            duration_ms = (time.time() - start_time) * 1000
            
            intent_classification = final_state.get("intent_classification")
            
            logger.log_operation(
                component="orchestrator",
                operation="process_query",
                phase="complete", 
                outcome="success",
                duration_ms=duration_ms,
                intent=intent_classification.intent.value if intent_classification else "unknown",
                tools_used=len(final_state.get("tool_calls", [])),
                confidence=intent_classification.confidence if intent_classification else 0
            )
            
            return {
                "response": final_state["response"],
                "intent": intent_classification.intent.value if intent_classification else "unknown",
                "confidence": intent_classification.confidence if intent_classification else 0,
                "trace_id": trace_id,
                "execution_path": final_state.get("execution_path", []),
                "performance": {
                    "duration_ms": duration_ms,
                    "tool_calls": len(final_state.get("tool_calls", [])),
                    "retry_count": final_state.get("retry_count", 0)
                }
            }
            
        except Exception as e:
            duration_ms = (time.time() - start_time) * 1000
            
            logger.log_error(
                component="orchestrator",
                operation="process_query",
                error=e,
                duration_ms=duration_ms,
                query=query
            )
            
            # Graceful fallback
            fallback_response = self._generate_fallback_response(query, str(e))
            
            return {
                "response": fallback_response,
                "intent": "error",
                "confidence": 0.1,
                "trace_id": trace_id,
                "error": str(e),
                "performance": {
                    "duration_ms": duration_ms,
                    "tool_calls": 0,
                    "retry_count": 0
                }
            }
        finally:
            # This block will execute whether there was an exception or not.
            end_time = time.time()
            duration_ms = (end_time - start_time) * 1000

            if 'final_state' in locals() and final_state:
                intent_classification = final_state.get("intent_classification")
                
                # Safely access attributes only if intent_classification is not None
                intent_value = "unknown"
                confidence_value = 0
                if intent_classification and hasattr(intent_classification, 'intent') and hasattr(intent_classification, 'confidence'):
                    intent_value = intent_classification.intent.value
                    confidence_value = intent_classification.confidence

                logger.log_operation(
                    component="orchestrator",
                    operation="process_query",
                    phase="complete", 
                    outcome="success",
                    duration_ms=duration_ms,
                    intent=intent_value,
                    tools_used=len(final_state.get("tool_calls", [])),
                    confidence=confidence_value
                )
                
                return {
                    "response": final_state.get("response", "No response generated."),
                    "intent": intent_value,
                    "confidence": confidence_value,
                    "trace_id": trace_id,
                    "execution_path": final_state.get("execution_path", []),
                    "performance": {
                        "duration_ms": duration_ms,
                        "tool_calls": len(final_state.get("tool_calls", [])),
                        "retry_count": final_state.get("retry_count", 0)
                    }
                }
            else:
                # This case is hit if `ainvoke` fails and throws an exception
                # The exception is already logged by the `except` block
                return {
                    "response": "I'm sorry, but I encountered an error and couldn't process your request.",
                    "intent": "error",
                    "confidence": 1.0,
                    "trace_id": trace_id,
                    "execution_path": [],
                    "performance": {"duration_ms": duration_ms, "tool_calls": 0, "retry_count": 0}
                }
    
    @log_performance("orchestrator", "route")
    async def _route_node(self, state: dict) -> dict:
        """Route query using modern intent classification."""
        
        logger.warning(f"🚦 ROUTE DEBUG: Starting route node for query: '{state['query']}'")
        execution_path = state["execution_path"] + ["route"]
        
        try:
            # Classify intent with conversation context
            logger.warning(f"🚦 ROUTE DEBUG: Calling router.classify_intent()")
            classification = self.router.classify_intent(
                state["query"],
                state["conversation_context"]
            )
            
            logger.warning(f"🚦 ROUTE DEBUG: Intent classification complete: {classification.intent.value} (confidence: {classification.confidence})")
            logger.warning(f"🚦 ROUTE DEBUG: Requires tools: {classification.requires_tools}")
            logger.warning(f"🚦 ROUTE DEBUG: Entities found: {classification.entities}")
            
            # Determine route
            if classification.intent == IntentType.ABUSE:
                route_decision = "abuse"
            elif classification.intent == IntentType.CONVERSATION:
                route_decision = "conversation"
            elif classification.intent == IntentType.SCHEMA:
                route_decision = "schema_task"
            elif classification.intent in [IntentType.DATA_ANALYSIS, IntentType.GENERAL]:
                route_decision = "data_task"
            elif classification.intent == IntentType.FOLLOW_UP:
                route_decision = "follow_up"
            else:
                route_decision = "schema_task"  # Safe default
                
            logger.warning(f"🚦 ROUTE DEBUG: Route decision made: {route_decision}")
            
            logger.log_operation(
                component="router",
                operation="classify",
                phase="complete",
                outcome="success",
                intent=classification.intent.value,
                confidence=classification.confidence,
                entities_count=sum(len(v) for v in classification.entities.values())
            )
            
            return {
                "execution_path": execution_path,
                "intent_classification": classification,
                "needs_tools": classification.requires_tools,
                "entities": classification.entities,
                "context_carryover": classification.context_carryover,
                "confidence_score": classification.confidence,
                "route_decision": route_decision
            }
            
        except Exception as e:
            logger.log_error("router", "classify", e)
            errors = state["errors"] + [f"Routing failed: {e}"]
            return {
                "execution_path": execution_path,
                "route_decision": "error",
                "errors": errors
            }
    
    @log_performance("orchestrator", "conversation")
    async def _conversation_node(self, state: dict) -> dict:
        """Handle conversational interactions using LLM for dynamic responses."""
        
        logger.warning(f"💬 CONVERSATION DEBUG: Entering conversation node")
        logger.warning(f"💬 CONVERSATION DEBUG: Query: '{state['query']}'")
        logger.warning(f"💬 CONVERSATION DEBUG: Intent classification: {state.get('intent_classification', 'None')}")
        
        state["execution_path"].append("conversation")
        
        try:
            classification = state["intent_classification"]
            query = state["query"].lower().strip()
            
            logger.warning(f"💬 CONVERSATION DEBUG: Processing query type, classification intent: {classification.intent.value if classification else 'None'}")
            
            if classification and classification.intent == IntentType.ABUSE:
                logger.warning(f"💬 CONVERSATION DEBUG: Handling abuse case")
                # Handle abuse with brief redirect
                response = self.safety.handle_abuse(query, state["conversation_context"])
            
            else:
                # Use LLM to generate contextual conversation responses
                logger.warning(f"💬 CONVERSATION DEBUG: Using LLM for dynamic conversation response")
                
                conversation_prompt = f"""You are an AML (Anti-Money Laundering) database assistant. Respond to the user's conversational query naturally and helpfully.

                    User Query: "{state['query']}"

                    Context: This is a conversational interaction (greeting, help request, or general question about your capabilities).

                    Generate a friendly, informative response that:
                    - Acknowledges their query appropriately
                    - Briefly explains your AML database analysis capabilities
                    - Offers specific examples of what you can help with
                    - Invites them to ask a specific question

                    Keep the response concise but helpful (2-4 sentences max)."""

                try:
                    if hasattr(self, 'llm_manager') and self.llm_manager:
                        messages = [{"role": "user", "content": conversation_prompt}]
                        llm_response = self.llm_manager.chat(messages)
                        response = llm_response.content if hasattr(llm_response, 'content') else str(llm_response)
                        logger.warning(f"💬 CONVERSATION DEBUG: LLM generated response: {response[:100]}...")
                    else:
                        # Fallback only if no LLM available
                        response = "Hello! I'm your AML database assistant. I can help you explore database schemas, analyze data patterns, and answer questions about your AML system. What would you like to explore?"
                        logger.warning(f"💬 CONVERSATION DEBUG: Using fallback response (no LLM)")
                        
                except Exception as llm_error:
                    logger.warning(f"💬 CONVERSATION DEBUG: LLM failed: {llm_error}, using fallback")
                    response = "Hello! I'm your AML database assistant. I can help you explore database schemas, analyze data patterns, and answer questions about your AML system. What would you like to explore?"
            
            state["response"] = response
            state["confidence_score"] = 0.95
            
            logger.log_operation(
                component="conversation",
                operation="respond",
                phase="complete", 
                outcome="success",
                response_length=len(response),
                conversation_type=classification.intent.value if classification else "unknown"
            )
            
        except Exception as e:
            logger.log_error("conversation", "respond", e)
            state["response"] = "I'm here to help with AML database questions. What can I assist you with?"
            state["errors"].append(f"Conversation handling failed: {e}")
        
        return state
    
    @log_performance("orchestrator", "schema_retrieve")
    async def _schema_retrieve_node(self, state: dict) -> dict:
        """Retrieve relevant schema information using vector search only."""
        
        print("🔍 SCHEMA RETRIEVE NODE STARTED")  # Simple print to see if node executes
        logger.warning(f"🗄️ SCHEMA DEBUG: Entering schema retrieve node")
        logger.warning(f"🗄️ SCHEMA DEBUG: Query: '{state['query']}'")
        logger.warning(f"🗄️ SCHEMA DEBUG: Current entities: {state.get('entities', {})}")
        
        state["execution_path"].append("schema_retrieve")
        
        try:
            query = state["query"]
            
            # Use vector search to find relevant schema information  
            # Import VectorOnlyRetriever from langgraph_orchestrator
            try:
                from .langgraph_orchestrator import VectorOnlyRetriever
                vector_retriever = VectorOnlyRetriever()
                
                # Search for schema information in vector database
                vector_results = vector_retriever.semantic_search(query, max_results=10)
                
                logger.warning(f"🗄️ SCHEMA DEBUG: Vector search found {len(vector_results)} results")
                
                # Debug: Print first few results
                for i, result in enumerate(vector_results[:3]):
                    logger.warning(f"🗄️ SCHEMA DEBUG: Result {i+1}: {result.get('content', '')[:100]}...")
                    logger.warning(f"🗄️ SCHEMA DEBUG: Result {i+1} metadata: {result.get('metadata', {})}")
                
                if vector_results:
                    # Convert vector results to schema format for compatibility
                    schema_results = {
                        "tables": [],
                        "columns": [],
                        "total_results": len(vector_results),
                        "vector_results": vector_results
                    }
                    
                    # Try to extract table information from results
                    for result in vector_results:
                        content = result.get("content", "").upper()
                        metadata = result.get("metadata", {})
                        
                        # Extract table names from metadata first (more reliable)
                        if "table_name" in metadata:
                            table_name = metadata["table_name"]
                            if table_name and table_name not in schema_results["tables"]:
                                schema_results["tables"].append(table_name)
                                logger.warning(f"🗄️ SCHEMA DEBUG: Found table from metadata: {table_name}")
                        
                        # Also try content-based extraction as fallback
                        if "TABLE" in content or "PIO_" in content or "BI_DWH" in content:
                            # Extract potential table names
                            words = content.split()
                            table_names = [word.replace(":", "").replace(",", "") for word in words if 
                                         word.startswith("PIO_") or 
                                         word.startswith("BI_DWH")]
                            for table_name in table_names:
                                if table_name and table_name not in schema_results["tables"]:
                                    schema_results["tables"].append(table_name)
                                    logger.warning(f"🗄️ SCHEMA DEBUG: Found table from content: {table_name}")
                    
                    # Remove duplicates
                    schema_results["tables"] = list(set(schema_results["tables"]))
                    
                    logger.warning(f"🗄️ SCHEMA DEBUG: Extracted {len(schema_results['tables'])} potential table references")
                    
                else:
                    schema_results = {
                        "tables": [],
                        "columns": [],
                        "total_results": 0,
                        "vector_results": []
                    }
                    logger.warning(f"🗄️ SCHEMA DEBUG: No vector results found")
                
            except Exception as vector_error:
                logger.warning(f"🗄️ SCHEMA DEBUG: Vector retrieval failed: {vector_error}, using fallback")
                schema_results = {
                    "tables": [],
                    "columns": [],
                    "total_results": 0,
                    "vector_results": [],
                    "error": str(vector_error)
                }
            
            state["schema_retrieved"] = schema_results
            
            # Record tool usage
            state["tool_calls"].append({
                "tool": "vector_schema_retriever",
                "input": query,
                "output_size": len(schema_results.get("vector_results", [])),
                "timestamp": time.time()
            })
            
            logger.log_operation(
                component="schema_retriever",
                operation="retrieve_schemas", 
                phase="complete",
                outcome="success" if schema_results.get("total_results", 0) > 0 else "empty",
                search_terms_count=1,
                tables_found=len(schema_results.get("tables", []))
            )
            
        except Exception as e:
            logger.log_error("schema_retriever", "retrieve", e)
            state["schema_retrieved"] = schema_results
            
            # Record tool usage
            state["tool_calls"].append({
                "tool": "vector_schema_retriever",
                "input": query,
                "output_size": len(schema_results.get("vector_results", [])),
                "timestamp": time.time()
            })
            
            logger.log_operation(
                component="schema_retriever",
                operation="retrieve_schemas", 
                phase="complete",
                outcome="success" if schema_results.get("total_results", 0) > 0 else "empty",
                search_terms_count=1,
                tables_found=len(schema_results.get("tables", []))
            )
            
        except Exception as e:
            logger.log_error("schema_retriever", "retrieve", e)
            state["schema_retrieved"] = {"tables": [], "columns": [], "total_results": 0}
            state["errors"].append(f"Schema retrieval failed: {e}")
        
        return state
    
    @log_performance("orchestrator", "sql_generate")
    async def _sql_generate_node(self, state: dict) -> dict:
        """Generate SQL query based on intent and schema."""
        
        state["execution_path"].append("sql_generate")
        
        try:
            schema_context = state["schema_retrieved"]
            classification = state["intent_classification"]
            
            # Generate SQL with enhanced context
            sql_result = await self.sql_generator.generate_sql(
                query=state["query"],
                intent=classification.intent.value if classification else "general",
                schema_context=schema_context,
                conversation_context=state["conversation_context"],
                entities=state["entities"]
            )
            
            state["sql_generated"] = sql_result.get("sql", "")
            
            # Record tool usage
            state["tool_calls"].append({
                "tool": "sql_generator", 
                "input": {
                    "query": state["query"],
                    "schema_tables": len(schema_context.get("tables", []))
                },
                "output": state["sql_generated"],
                "timestamp": time.time()
            })
            
            logger.log_operation(
                component="sql_generator",
                operation="generate",
                phase="complete",
                outcome="success" if state["sql_generated"] else "empty",
                sql_length=len(state["sql_generated"]),
                schema_tables_used=len(schema_context.get("tables", []))
            )
            
        except Exception as e:
            logger.log_error("sql_generator", "generate", e)
            state["sql_generated"] = ""
            state["errors"].append(f"SQL generation failed: {e}")
        
        return state
    
    @log_performance("orchestrator", "sql_validate")
    async def _sql_validate_node(self, state: dict) -> dict:
        """Validate SQL for safety and correctness."""
        
        state["execution_path"].append("sql_validate")
        
        try:
            sql_query = state["sql_generated"]
            
            # Enhanced safety validation
            validation_result = self.safety.validate_sql_safety(sql_query)
            
            state["sql_validated"] = validation_result
            
            logger.log_operation(
                component="sql_validator",
                operation="validate", 
                phase="complete",
                outcome="safe" if validation_result.get("safe") else "unsafe",
                sql_length=len(sql_query),
                validation_reason=validation_result.get("reason", "")
            )
            
        except Exception as e:
            logger.log_error("sql_validator", "validate", e)
            state["sql_validated"] = {"safe": False, "error": str(e)}
            state["errors"].append(f"SQL validation failed: {e}")
        
        return state
    
    @log_performance("orchestrator", "sql_execute")
    async def _sql_execute_node(self, state: dict) -> dict:
        """Execute validated SQL query."""
        
        state["execution_path"].append("sql_execute")
        
        try:
            sql_query = state["sql_generated"]
            
            # Execute with safety limits
            execution_result = await self.sql_executor.execute_query(
                sql_query=sql_query,
                limit=100,  # Safety limit
                timeout_seconds=30
            )
            
            state["sql_results"] = execution_result.get("results", [])
            
            # Record tool usage
            state["tool_calls"].append({
                "tool": "sql_executor",
                "input": sql_query,
                "output_rows": len(state["sql_results"]),
                "timestamp": time.time()
            })
            
            logger.log_operation(
                component="sql_executor", 
                operation="execute",
                phase="complete",
                outcome="success" if state["sql_results"] is not None else "error",
                rows_returned=len(state["sql_results"]) if state["sql_results"] else 0,
                sql_length=len(sql_query)
            )
            
        except Exception as e:
            logger.log_error("sql_executor", "execute", e)
            state["sql_results"] = []
            state["errors"].append(f"SQL execution failed: {e}")
        
        return state
    
    @log_performance("orchestrator", "compose_answer")
    async def _compose_answer_node(self, state: dict) -> dict:
        """Compose natural language answer from SQL results or vector search."""
        state["execution_path"].append("compose_answer")
        try:
            # For schema queries, use vector_results as results
            results = state["sql_results"]
            schema_ctx = state.get("schema_retrieved", {})
            # Always use vector_results if present and non-empty
            if schema_ctx.get("vector_results"):
                results = schema_ctx["vector_results"]
                import pprint
                debug_msg = f"🟦 DEBUG: Passing {len(results) if results else 0} results to compose_answer for schema query (vector_results present)"
                print(debug_msg)
                logger.warning(debug_msg)
                if results:
                    debug_first = f"🟦 DEBUG: First result: {pprint.pformat(results[0])}"
                    print(debug_first)
                    logger.warning(debug_first)
                debug_ctx = f"🟦 DEBUG: Schema context: {pprint.pformat(schema_ctx)}"
                print(debug_ctx)
                logger.warning(debug_ctx)
            composed_result = await self.answer_composer.compose_answer(
                query=state["query"],
                sql_query=state.get("sql_generated"),
                results=results,
                schema_context=state.get("schema_retrieved", {}),
                conversation_context=state.get("conversation_context", {})
            )
            state["final_answer"] = composed_result.get("answer", "")
            state["response"] = state["final_answer"]
            # Update confidence based on results
            if state.get("sql_results"):
                state["confidence_score"] = min(0.9, state["confidence_score"] + 0.3)
            logger.log_operation(
                component="answer_composer",
                operation="compose",
                phase="complete", 
                outcome="success",
                answer_length=len(state["final_answer"]),
                results_rows=len(state["sql_results"]) if state.get("sql_results") else 0
            )
        except Exception as e:
            logger.log_error("answer_composer", "compose", e)
            # Use LLM to generate contextual error response
            try:
                if hasattr(self, 'llm_manager') and self.llm_manager:
                    error_prompt = f"I retrieved data but had formatting issues. Briefly explain this to the user and offer to help in other ways. Keep it helpful and concise."
                    messages = [{"role": "user", "content": error_prompt}]
                    llm_response = self.llm_manager.chat(messages)
                    error_response = llm_response.content if hasattr(llm_response, 'content') else str(llm_response)
                else:
                    error_response = f"I found some results but had trouble formatting them. The query returned {len(state['sql_results']) if state.get('sql_results') else 0} rows. Would you like me to try a different approach?"
            except:
                error_response = f"I found some results but had trouble formatting them. The query returned {len(state['sql_results']) if state.get('sql_results') else 0} rows. Would you like me to try a different approach?"
            state["response"] = error_response
            state["errors"].append(f"Answer composition failed: {e}")
        return state
    
    @log_performance("orchestrator", "save_memory")
    async def _save_memory_node(self, state: dict) -> dict:
        """Save conversation turn to memory."""
        
        state["execution_path"].append("save_memory")
        
        try:
            # Create conversation turn
            turn = ConversationTurn(
                turn_id=state["turn_id"],
                query=state["query"],
                intent=state["intent_classification"].intent if state["intent_classification"] else IntentType.GENERAL,
                entities=state["entities"],
                tools_used=[call["tool"] for call in state["tool_calls"]],
                response=state["response"],
                confidence=state["confidence_score"],
                timestamp=datetime.utcnow(),
                context_inherited=state["conversation_context"]
            )
            
            # Save to memory
            self.memory.add_turn(state["session_id"], turn)
            
            logger.log_operation(
                component="memory",
                operation="save_turn",
                phase="complete",
                outcome="success",
                turn_id=state["turn_id"],
                session_id=state["session_id"]
            )
            
        except Exception as e:
            logger.log_error("memory", "save_turn", e)
            state["errors"].append(f"Memory save failed: {e}")
        
        return state
    
    async def _handle_error_node(self, state: AgentState) -> AgentState:
        """Handle errors with informative LLM-generated responses."""
        
        state["execution_path"].append("handle_error")
        
        # Use LLM to generate contextual error responses
        error_context = str(state["errors"])
        user_query = state["query"]
        
        error_prompt = f"""You are an AML database assistant. The user's query failed to process. Generate a helpful, encouraging response.

User Query: "{user_query}"
Error Context: {error_context}

Generate a response that:
- Acknowledges the issue briefly and professionally
- Provides 2-3 specific, actionable suggestions for the user
- Maintains a helpful tone and offers to continue assisting
- Focuses on AML database topics they can explore instead

Keep it concise and solution-oriented (3-4 sentences max)."""

        try:
            if hasattr(self, 'llm_manager') and self.llm_manager:
                messages = [{"role": "user", "content": error_prompt}]
                llm_response = self.llm_manager.chat(messages)
                response = llm_response.content if hasattr(llm_response, 'content') else str(llm_response)
                logger.warning(f"🔄 ERROR HANDLER DEBUG: LLM generated error response")
            else:
                # Fallback only if no LLM available
                if "SQL generation failed" in error_context:
                    response = "I had trouble generating a SQL query for your request. Could you try being more specific about which tables you're interested in, or ask about table structures first?"
                elif "Schema retrieval failed" in error_context:
                    response = "I couldn't find the relevant database schemas. Could you try asking about a specific table like 'PIO_ACCOUNTS' or 'BI_DWH tables'?"
                else:
                    response = "I encountered an issue processing your request. Please try asking about a specific table or rephrasing your question. I'm here to help with AML database questions!"
                
        except Exception as llm_error:
            logger.warning(f"🔄 ERROR HANDLER DEBUG: LLM failed: {llm_error}, using fallback")
            response = "I encountered an issue processing your request. Please try asking about a specific table or rephrasing your question. I'm here to help with AML database questions!"
        
        state["response"] = response
        
        state["confidence_score"] = 0.3
        
        logger.log_operation(
            component="error_handler",
            operation="handle_error",
            phase="complete",
            outcome="handled",
            error_count=len(state["errors"]),
            retry_count=state["retry_count"]
        )
        
        return state
    
    async def _self_heal_node(self, state: AgentState) -> AgentState:
        """Self-healing: retry with modifications or search widening."""
        
        state["execution_path"].append("self_heal")
        state["retry_count"] += 1
        
        logger.log_operation(
            component="self_healer",
            operation="attempt_heal",
            phase="start",
            outcome="attempting",
            retry_count=state["retry_count"],
            max_retries=state["max_retries"]
        )
        
        # Search widening strategies
        if not state["schema_retrieved"] or not state["schema_retrieved"].get("tables"):
            # Widen schema search
            broader_terms = ["PIO_", "BI_DWH", "ACCOUNTS", "TRANSACTIONS"]
            state["entities"]["tables"] = broader_terms
            state["context_carryover"].extend(broader_terms)
        
        elif state["sql_generated"] and not state["sql_results"]:
            # Simplify SQL or add fallbacks
            pass  # Could implement SQL simplification
        
        return state
    
    # Conditional edge functions
    def _route_decision(self, state: AgentState) -> str:
        """Decide routing based on classification."""
        return state["route_decision"]
    
    def _check_retrieval_success(self, state: AgentState) -> str:
        """Check if vector schema retrieval was successful."""
        if state["errors"] and "Schema retrieval failed" in str(state["errors"]):
            return "error"
        elif not state["schema_retrieved"] or state["schema_retrieved"].get("total_results", 0) == 0:
            if state["retry_count"] < state["max_retries"]:
                return "empty_retry"
            else:
                return "error"
        else:
            return "success"
    
    def _check_generation_success(self, state: AgentState) -> str:
        """Check if SQL generation was successful.""" 
        if state["errors"] and "SQL generation failed" in str(state["errors"]):
            return "error"
        elif not state["sql_generated"]:
            if state["retry_count"] < state["max_retries"]:
                return "retry"
            else:
                return "error"
        else:
            return "success"
    
    def _check_validation_success(self, state: AgentState) -> str:
        """Check if SQL validation passed."""
        validation = state["sql_validated"]
        if not validation:
            return "error"
        elif not validation.get("safe", False):
            return "unsafe"
        else:
            return "safe"
    
    def _check_execution_success(self, state: AgentState) -> str:
        """Check if SQL execution was successful."""
        if state["errors"] and "SQL execution failed" in str(state["errors"]):
            if state["retry_count"] < state["max_retries"]:
                return "retry"
            else:
                return "error"
        elif state["sql_results"] is None:
            return "error"
        else:
            return "success"
    
    def _self_heal_decision(self, state: AgentState) -> str:
        """Decide how to self-heal based on the failure point."""
        if state["retry_count"] >= state["max_retries"]:
            return "give_up"
        
        # Determine what to retry based on where we failed
        if not state["schema_retrieved"] or not state["schema_retrieved"].get("tables"):
            return "retry_schema"
        elif not state["sql_generated"]:
            return "retry_sql"
        elif state["sql_results"] is None:
            return "retry_execute"
        else:
            return "give_up"
    
    def _generate_fallback_response(self, query: str, error: str) -> str:
        """Generate graceful fallback response for system failures."""
        return f"""I apologize, but I'm having technical difficulties processing your request right now. 

Please try asking about:
• Specific database tables (e.g., "Show me PIO_ACCOUNTS structure")
• Data analysis questions (e.g., "How many records in [table]?")
• Schema exploration (e.g., "What tables contain customer data?")

I'll do my best to help once the issue is resolved."""