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
    """Rich state for modern agentic workflow with enhanced memory."""
    # Core conversation
    session_id: str
    turn_id: str
    query: str
    response: str
    
    # Enhanced Memory Management
    conversation_summary: str  # Rolling summary of the conversation
    context_stack: List[str]   # Most recent tables/entities user asked about
    last_columns: Dict[str, List[str]]  # Last referenced columns per table
    recent_turns: List[Dict[str, str]]  # Last 6-10 user/assistant turns
    
    # Intent and routing
    intent_classification: Optional[IntentClassification]
    needs_tools: bool
    route_decision: str
    
    # Context and memory (legacy - keeping for compatibility)
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
        self.memory = ConversationMemory(Path(config.get("memory_path", "memory")) / "sessions")
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
                "performance_metrics": {},
                # Enhanced memory fields
                "conversation_summary": "",
                "context_stack": [],
                "last_columns": {},
                "recent_turns": []
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
        
        print(f"🚦 ROUTE DEBUG: Starting route node for query: '{state['query']}'")
        execution_path = state["execution_path"] + ["route"]
        
        try:
            # Build enhanced prompt with memory context
            route_payload = {"query": state["query"]}
            enhanced_query = self.build_prompt(state, route_payload)
            
            # Store enhanced query in state for use by other nodes
            state["enhanced_query"] = enhanced_query
            
            # Classify intent with conversation context
            print(f"🚦 ROUTE DEBUG: Calling router.classify_intent() with enhanced query")
            classification = self.router.classify_intent(
                enhanced_query,
                state["conversation_context"]
            )
            
            print(f"🚦 ROUTE DEBUG: Intent classification complete: {classification.intent.value} (confidence: {classification.confidence})")
            print(f"🚦 ROUTE DEBUG: Requires tools: {classification.requires_tools}")
            print(f"🚦 ROUTE DEBUG: Entities found: {classification.entities}")
            
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
                
            print(f"🚦 ROUTE DEBUG: Route decision made: {route_decision}")
            
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
        
        print(f"💬 CONVERSATION DEBUG: Entering conversation node")
        print(f"💬 CONVERSATION DEBUG: Query: '{state['query']}'")
        print(f"💬 CONVERSATION DEBUG: Intent classification: {state.get('intent_classification', 'None')}")
        
        state["execution_path"].append("conversation")
        
        try:
            classification = state["intent_classification"]
            query = state["query"].lower().strip()
            
            print(f"💬 CONVERSATION DEBUG: Processing query type, classification intent: {classification.intent.value if classification else 'None'}")
            
            if classification and classification.intent == IntentType.ABUSE:
                print(f"💬 CONVERSATION DEBUG: Handling abuse case")
                # Handle abuse with brief redirect
                response = self.safety.handle_abuse(query, state["conversation_context"])
            
            else:
                # Use LLM to generate contextual conversation responses
                print(f"💬 CONVERSATION DEBUG: Using LLM for dynamic conversation response")
                
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
                        print(f"💬 CONVERSATION DEBUG: LLM generated response: {response[:100]}...")
                    else:
                        # Fallback only if no LLM available
                        response = "Hello! I'm your AML database assistant. I can help you explore database schemas, analyze data patterns, and answer questions about your AML system. What would you like to explore?"
                        print(f"💬 CONVERSATION DEBUG: Using fallback response (no LLM)")
                        
                except Exception as llm_error:
                    print(f"💬 CONVERSATION DEBUG: LLM failed: {llm_error}, using fallback")
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
        print(f"🗄️ SCHEMA DEBUG: Entering schema retrieve node")
        print(f"🗄️ SCHEMA DEBUG: Query: '{state['query']}'")
        print(f"🗄️ SCHEMA DEBUG: Current entities: {state.get('entities', {})}")
        
        state["execution_path"].append("schema_retrieve")
        
        try:
            # Build context-aware search query
            base_query = state["query"]
            entities = state.get("entities", {})
            context_carryover = state.get("context_carryover", [])
            conversation_context = state.get("conversation_context", {})
            
            # For follow-up queries, prioritize context entities over raw query
            search_terms = []
            
            # Add entities from current classification
            for entity_type, entity_list in entities.items():
                if entity_list and entity_type in ['tables', 'columns']:
                    search_terms.extend(entity_list)
            
            # Add context carryover (from previous turns)
            if context_carryover:
                search_terms.extend(context_carryover)
            
            # Add recent entities from memory
            recent_entities = conversation_context.get("recent_entities", {})
            for entity_type, entity_list in recent_entities.items():
                if entity_list and entity_type in ['tables', 'columns']:
                    search_terms.extend(entity_list[:2])  # Top 2 recent entities
            
            # If we have specific entities to search for, use them; otherwise use the raw query
            if search_terms:
                # Create context-aware query
                unique_terms = list(set(search_terms))  # Remove duplicates
                query = f"{' '.join(unique_terms)} {base_query}"  # Combine entities with query
                print(f"🗄️ SCHEMA DEBUG: Context-aware query: '{query}'")
                print(f"🗄️ SCHEMA DEBUG: Search terms from context: {unique_terms}")
            else:
                query = base_query
                print(f"🗄️ SCHEMA DEBUG: Using base query (no context): '{query}'")
            
            # Use vector search to find relevant schema information  
            # Import VectorOnlyRetriever from langgraph_orchestrator
            try:
                # Initialize schema_results at the start to avoid UnboundLocalError
                schema_results = {
                    "tables": [],
                    "columns": [],
                    "total_results": 0,
                    "vector_results": []
                }
                
                from .langgraph_orchestrator import VectorOnlyRetriever
                vector_retriever = VectorOnlyRetriever()
                
                # Search for schema information in vector database
                vector_results = vector_retriever.semantic_search(query, max_results=10)
                
                print(f"🗄️ SCHEMA DEBUG: Vector search found {len(vector_results)} results")
                
                # Debug: Print first few results
                for i, result in enumerate(vector_results[:3]):
                    print(f"🗄️ SCHEMA DEBUG: Result {i+1}: {result.get('content', '')[:100]}...")
                    print(f"🗄️ SCHEMA DEBUG: Result {i+1} metadata: {result.get('metadata', {})}")
                
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
                                print(f"🗄️ SCHEMA DEBUG: Found table from metadata: {table_name}")
                        
                        # ===========================================================================================
                        # Buring this delete it
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
                                    print(f"🗄️ SCHEMA DEBUG: Found table from content: {table_name}")
                    # ===========================================================================================
                    # Remove duplicates
                    schema_results["tables"] = list(set(schema_results["tables"]))
                    
                    print(f"🗄️ SCHEMA DEBUG: Extracted {len(schema_results['tables'])} potential table references")
                    
                else:
                    schema_results = {
                        "tables": [],
                        "columns": [],
                        "total_results": 0,
                        "vector_results": []
                    }
                    print(f"🗄️ SCHEMA DEBUG: No vector results found")
                
            except Exception as vector_error:
                print(f"🗄️ SCHEMA DEBUG: Vector retrieval failed: {vector_error}, using fallback")
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
                print(debug_msg)
                if results:
                    debug_first = f"🟦 DEBUG: First result: {pprint.pformat(results[0])}"
                    print(debug_first)
                    print(debug_first)
                debug_ctx = f"🟦 DEBUG: Schema context: {pprint.pformat(schema_ctx)}"
                print(debug_ctx)
                print(debug_ctx)
            # Use enhanced query if available, otherwise fall back to basic query
            query_to_use = state.get("enhanced_query", state["query"])
            print(f"🔧 DEBUG compose_answer: Using {'enhanced' if 'enhanced_query' in state else 'basic'} query")
            
            composed_result = await self.answer_composer.compose_answer(
                query=query_to_use,
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
        """Save conversation turn to memory with enhanced memory management."""
        
        state["execution_path"].append("save_memory")
        print(f"🧠 SAVE_MEMORY_NODE: Called for session {state['session_id']}")
        
        try:
            # Update enhanced memory using helper function
            memory_updates = self.update_memory(
                state, 
                state["query"], 
                state.get("entities", {})
            )
            
            # Merge memory updates into state
            state.update(memory_updates)
            
            # Create conversation turn for traditional memory
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
            
            print(f"🧠 SAVE_MEMORY_NODE: Saving turn: {turn.query[:50]}...")
            # Save to traditional memory
            self.memory.add_turn(state["session_id"], turn)
            print(f"🧠 SAVE_MEMORY_NODE: Turn saved successfully")
            
            logger.log_operation(
                component="memory",
                operation="save_turn",
                phase="complete",
                outcome="success",
                turn_id=state["turn_id"],
                session_id=state["session_id"],
                enhanced_memory=True
            )
            
        except Exception as e:
            print(f"🧠 SAVE_MEMORY_NODE: ERROR - {e}")
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
                print(f"🔄 ERROR HANDLER DEBUG: LLM generated error response")
            else:
                # Fallback only if no LLM available
                if "SQL generation failed" in error_context:
                    response = "I had trouble generating a SQL query for your request. Could you try being more specific about which tables you're interested in, or ask about table structures first?"
                elif "Schema retrieval failed" in error_context:
                    response = "I couldn't find the relevant database schemas. Could you try asking about a specific table like 'PIO_ACCOUNTS' or 'BI_DWH tables'?"
                else:
                    response = "I encountered an issue processing your request. Please try asking about a specific table or rephrasing your question. I'm here to help with AML database questions!"
                
        except Exception as llm_error:
            print(f"🔄 ERROR HANDLER DEBUG: LLM failed: {llm_error}, using fallback")
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
    
    def update_memory(self, state: AgentState, user_input: str, entities: Dict[str, Any] = None) -> Dict[str, Any]:
        """Update conversation memory with new turn information."""
        # Initialize entities if not provided
        if entities is None:
            entities = {}
        
        # Extract table/column references from user input and entities
        mentioned_tables = entities.get('tables', [])
        mentioned_columns = entities.get('columns', [])
        
        # Update recent turns (keep last 5 turns)
        recent_turns = state.get("recent_turns", [])
        new_turn = {
            "user": user_input,
            "timestamp": str(datetime.now()),
            "tables": mentioned_tables,
            "columns": mentioned_columns
        }
        recent_turns.append(new_turn)
        if len(recent_turns) > 5:
            recent_turns = recent_turns[-5:]
        
        # Update last columns accessed (keep per table)
        last_columns = state.get("last_columns", {})
        for table in mentioned_tables:
            if table not in last_columns:
                last_columns[table] = []
            last_columns[table].extend(mentioned_columns)
            # Keep only unique columns, last 10 per table
            last_columns[table] = list(dict.fromkeys(last_columns[table]))[-10:]
        
        # Update context stack (key concepts/topics)
        context_stack = state.get("context_stack", [])
        if mentioned_tables or mentioned_columns:
            context_item = f"Discussed: {', '.join(mentioned_tables)} tables"
            if mentioned_columns:
                context_item += f" and {', '.join(mentioned_columns)} columns"
            context_stack.append(context_item)
            # Keep last 10 context items
            if len(context_stack) > 10:
                context_stack = context_stack[-10:]
        
        # Update conversation summary (summarize every 3 turns)
        conversation_summary = state.get("conversation_summary", "")
        if len(recent_turns) % 3 == 0 and len(recent_turns) > 0:
            # Create a simple summary of recent activity
            recent_tables = set()
            recent_topics = []
            for turn in recent_turns[-3:]:
                recent_tables.update(turn.get('tables', []))
                if turn.get('user'):
                    # Extract key topics from user input
                    if any(word in turn['user'].lower() for word in ['count', 'how many', 'records']):
                        recent_topics.append("data counting")
                    elif any(word in turn['user'].lower() for word in ['structure', 'columns', 'schema']):
                        recent_topics.append("schema exploration")
                    elif any(word in turn['user'].lower() for word in ['join', 'relationship', 'connect']):
                        recent_topics.append("table relationships")
            
            if recent_tables or recent_topics:
                summary_parts = []
                if recent_tables:
                    summary_parts.append(f"Working with: {', '.join(sorted(recent_tables))}")
                if recent_topics:
                    summary_parts.append(f"Focus: {', '.join(set(recent_topics))}")
                conversation_summary = "; ".join(summary_parts)
        
        return {
            "conversation_summary": conversation_summary,
            "context_stack": context_stack,
            "last_columns": last_columns,
            "recent_turns": recent_turns
        }
    
    def build_prompt(self, state: AgentState, route_payload: Dict[str, Any]) -> str:
        """Build enhanced prompt incorporating memory spine."""
        base_query = route_payload.get('query', '')
        
        # Get memory components from conversation_context (this is the actual memory data)
        conversation_context = state.get("conversation_context", {})
        conversation_summary = conversation_context.get("session_summary", "")
        recent_turns = conversation_context.get("recent_turns", [])
        recent_entities = conversation_context.get("recent_entities", {})
        active_topics = conversation_context.get("active_topics", [])
        turn_count = conversation_context.get("turn_count", 0)
        
        print(f'🔧 BUILD_PROMPT: base_query={base_query}')
        print(f'🔧 BUILD_PROMPT: turn_count={turn_count}')
        print(f'🔧 BUILD_PROMPT: recent_turns={recent_turns}')
        print(f'🔧 BUILD_PROMPT: recent_entities={recent_entities}')
        
        # Build memory context
        memory_context = []
        
        if conversation_summary:
            memory_context.append(f"Previous conversation: {conversation_summary}")
        
        if turn_count > 0:
            memory_context.append(f"This is turn #{turn_count + 1} in the conversation")
        
        if recent_turns:
            memory_context.append(f"Previous queries: {', '.join(recent_turns[-2:])}")  # Last 2 queries
        
        if recent_entities:
            # Add recently mentioned entities
            for entity_type, entities in recent_entities.items():
                if entities and entity_type in ['tables', 'columns']:
                    memory_context.append(f"Recently discussed {entity_type}: {', '.join(entities[:3])}")
        
        if active_topics:
            memory_context.append(f"Active topics: {', '.join(active_topics[:3])}")
        
        # Combine memory with current query
        if memory_context:
            enhanced_prompt = f"""Memory Context:
{chr(10).join(f"- {ctx}" for ctx in memory_context)}

Current Query: {base_query}

Please consider the conversation history and previously accessed tables/columns when responding."""
        else:
            enhanced_prompt = base_query
        
        print(f'🔧 BUILD_PROMPT: Enhanced query length: {len(enhanced_prompt)}')
        print(f'🔧 BUILD_PROMPT: Enhanced query preview: {enhanced_prompt[:200]}...')
        
        return enhanced_prompt