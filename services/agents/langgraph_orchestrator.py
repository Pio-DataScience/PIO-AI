"""
Main LangGraph agent orchestrator for stateful, multi-tool interactions.
Implements the complete agent workflow with planning, execution, and memory.
"""

import json
import logging
import uuid
from typing import Dict, List, Optional, Any, Callable
from datetime import datetime
from pathlib import Path

# LangGraph imports
from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.memory import MemorySaver

# BGE and ChromaDB imports
try:
    import chromadb
    from chromadb.config import Settings
    from sentence_transformers import SentenceTransformer
    VECTOR_AVAILABLE = True
except ImportError:
    VECTOR_AVAILABLE = False

from .agentic_behavior import (
    AgentState, ConversationMemory, ConversationTurn,
    QueryRouter, SchemaRetriever, SQLGenerator, 
    SQLExecutor, AnswerComposer
)

logger = logging.getLogger(__name__)


class VectorOnlyRetriever:
    """
    Pure vector-based retrieval with intelligent query reformulation.
    Now uses EnhancedSemanticSearch for intent-aware retrieval.
    """
    
    def __init__(self, bge_model=None, chroma_client=None):
        """
        Initialize with enhanced search capability.
        
        Args:
            bge_model: Pre-loaded SentenceTransformer model (optional, for performance)
            chroma_client: Pre-initialized ChromaDB client (optional, for performance)
        """
        self.bge_model = bge_model  # Use provided model or load new one
        self.chroma_client = chroma_client  # Use provided client or create new one
        self.collections = {}
        self.enhanced_search = None  # Will use enhanced search if available
        
        if VECTOR_AVAILABLE:
            try:
                # Initialize BGE model only if not provided
                if self.bge_model is None:
                    logger.info("Loading BGE-large-en-v1.5 model...")
                    self.bge_model = SentenceTransformer('BAAI/bge-large-en-v1.5')
                    logger.info(f"BGE model loaded (dimension: {self.bge_model.get_sentence_embedding_dimension()})")
                else:
                    logger.info(f"Using pre-loaded BGE model (dimension: {self.bge_model.get_sentence_embedding_dimension()})")
                
                # Initialize ChromaDB only if not provided
                if self.chroma_client is None:
                    warehouse_path = Path("warehouse")
                    chroma_path = warehouse_path / "vectors"
                    
                    self.chroma_client = chromadb.PersistentClient(
                        path=str(chroma_path),
                        settings=Settings(
                            anonymized_telemetry=False,
                            allow_reset=True
                        )
                    )
                    logger.info("ChromaDB client initialized")
                else:
                    logger.info("Using pre-initialized ChromaDB client")
                
                # Load available collections
                collections = self.chroma_client.list_collections()
                primary_collection = None
                for collection in collections:
                    coll = self.chroma_client.get_collection(collection.name)
                    if coll.count() > 0:
                        self.collections[collection.name] = coll
                        logger.info(f"Loaded collection '{collection.name}' with {coll.count()} embeddings")
                        # Prioritize BGE-compatible dictionary metadata
                        if 'aml_dictionary_metadata_bge' in collection.name:
                            primary_collection = collection.name
                
                logger.info(f"Vector retrieval initialized with {len(self.collections)} collections")
                
                # Initialize enhanced search for intelligent retrieval
                if primary_collection and self.bge_model and self.chroma_client:
                    try:
                        from services.retriever.enhanced_semantic_search import EnhancedSemanticSearch
                        self.enhanced_search = EnhancedSemanticSearch(
                            chroma_client=self.chroma_client,
                            bge_model=self.bge_model,
                            collection_name=primary_collection
                        )
                        logger.info(f"🧠 VectorRetriever: Enhanced search enabled with query reformulation")
                    except Exception as e:
                        logger.warning(f"Enhanced search not available, using standard search: {e}")
                        self.enhanced_search = None
                
            except Exception as e:
                logger.error(f"Failed to initialize vector retrieval: {e}")
                self.bge_model = None
                self.chroma_client = None
        else:
            logger.warning("Vector libraries not available. Install: pip install chromadb sentence-transformers")
    
    def semantic_search(self, query: str, max_results: int = 10, session_id: str = None) -> List[Dict[str, Any]]:
        """
        Perform intelligent semantic search with query reformulation.
        Uses enhanced search when available for intent-aware retrieval.
        """
        if not self.bge_model or not self.collections:
            logger.warning("Vector search not available")
            return []
        
        # Try enhanced search first (with query reformulation)
        if self.enhanced_search:
            try:
                logger.info(f"VectorRetriever: Using enhanced search with query reformulation")
                
                results, retrieval_query = self.enhanced_search.search(
                    query=query,
                    max_results=max_results,
                    session_id=session_id
                )
                
                logger.info(
                    f"VectorRetriever: Query reformulated - "
                    f"Original: '{query[:50]}...' -> "
                    f"Reformulated: '{retrieval_query.reformulated_query[:50]}...' | "
                    f"Intent: {retrieval_query.intent.value} | "
                    f"Complete metadata: {retrieval_query.should_retrieve_complete_metadata}"
                )
                
                # Convert to expected format
                formatted_results = []
                for result in results:
                    formatted_results.append({
                        'content': result.get('document', ''),
                        'similarity_score': 1.0 - result.get('distance', 0.0),
                        'collection': self.enhanced_search.collection_name,
                        'metadata': result.get('metadata', {}),
                        'source': 'vector_bge_enhanced',
                        'intent': retrieval_query.intent.value,
                        'reformulated_query': retrieval_query.reformulated_query
                    })
                
                logger.info(f"VectorRetriever: Enhanced search returned {len(formatted_results)} results")
                return formatted_results
                
            except Exception as e:
                logger.error(f"VectorRetriever: Enhanced search failed: {e}, falling back to standard")
                # Fall through to standard search
        
        # Standard search fallback
        try:
            logger.info(f"VectorRetriever: Using standard search (no reformulation)")
            
            # Generate BGE embedding for query
            query_embedding = self.bge_model.encode([query])[0].tolist()
            
            all_results = []
            
            # Search in all collections
            for collection_name, collection in self.collections.items():
                try:
                    search_results = collection.query(
                        query_embeddings=[query_embedding],
                        n_results=min(max_results, collection.count())
                    )
                    
                    if search_results['documents'] and search_results['documents'][0]:
                        for doc, distance, metadata in zip(
                            search_results['documents'][0],
                            search_results['distances'][0],
                            search_results['metadatas'][0] or [{}] * len(search_results['documents'][0])
                        ):
                            similarity = 1.0 - distance
                            all_results.append({
                                'content': doc,
                                'similarity_score': similarity,
                                'collection': collection_name,
                                'metadata': metadata,
                                'source': 'vector_bge'
                            })
                
                except Exception as e:
                    logger.warning(f"Search failed for collection {collection_name}: {e}")
            
            # Sort by similarity and return top results
            all_results.sort(key=lambda x: x['similarity_score'], reverse=True)
            return all_results[:max_results]
            
        except Exception as e:
            logger.error(f"Semantic search failed: {e}")
            return []


class AgentOrchestrator:
    """
    Main orchestrator for the agentic RAG system using LangGraph.
    """
    
    def __init__(self, 
                 llm_provider,
                 oracle_dsn: str,
                 oracle_user: str,
                 oracle_password: str,
                 memory_path: Path = None):
        """
        Initialize the agent orchestrator.
        
        Args:
            llm_provider: LLM provider for answer generation and conversation
            oracle_dsn: Oracle database connection string
            oracle_user: Oracle username
            oracle_password: Oracle password
            memory_path: Path for conversation memory storage
        """
        self.llm_provider = llm_provider
        
        # Initialize components
        self.memory = ConversationMemory(
            memory_path or Path("data/agent_memory")
        )
        self.query_router = QueryRouter()
        
        # Initialize vector-only retrieval (no hybrid/BM25/graph)
        self.vector_retriever = VectorOnlyRetriever()
        
        self.sql_generator = SQLGenerator(None)  # Will use schema from vector search
        self.sql_executor = SQLExecutor(oracle_dsn, oracle_user, oracle_password)
        self.answer_composer = AnswerComposer(llm_provider)
        
        # Build the agent graph
        self.graph = self._build_agent_graph()
        
        logger.info("Agent orchestrator initialized with vector-only retrieval and LLM conversation")
    
    def _build_agent_graph(self) -> StateGraph:
        """Build the LangGraph workflow for the agent."""
        
        # Create the graph
        graph = StateGraph(AgentState)
        
        # Add nodes
        graph.add_node("route_query", self._route_query_node)
        graph.add_node("handle_conversation", self._handle_conversation_node)
        graph.add_node("retrieve_schema", self._retrieve_schema_node)
        graph.add_node("generate_sql", self._generate_sql_node)
        graph.add_node("execute_sql", self._execute_sql_node)
        graph.add_node("retrieve_general", self._retrieve_general_node)
        graph.add_node("compose_answer", self._compose_answer_node)
        graph.add_node("save_memory", self._save_memory_node)
        
        # Add edges with conditional routing
        graph.add_edge(START, "route_query")
        
        graph.add_conditional_edges(
            "route_query",
            self._route_decision,
            {
                "conversation": "handle_conversation",
                "schema": "retrieve_schema",
                "data_analysis": "generate_sql",
                "follow_up": "retrieve_schema",  # Follow-ups often need schema
                "general": "retrieve_general"
            }
        )
        
        graph.add_edge("handle_conversation", "save_memory")
        
        graph.add_edge("retrieve_schema", "compose_answer")
        graph.add_edge("generate_sql", "execute_sql")
        graph.add_edge("execute_sql", "compose_answer")
        graph.add_edge("retrieve_general", "compose_answer")
        graph.add_edge("compose_answer", "save_memory")
        graph.add_edge("save_memory", END)
        
        # Compile with memory
        memory_saver = MemorySaver()
        compiled_graph = graph.compile(checkpointer=memory_saver)
        
        return compiled_graph
    
    def _route_query_node(self, state: AgentState) -> AgentState:
        """Route the query and extract entities."""
        try:
            # Load conversation context
            context = self.memory.get_recent_context(state["session_id"])
            
            # Classify query type
            query_type = self.query_router.classify_query(state["query"], context)
            state["query_type"] = query_type
            
            # Extract entities
            entities = self.query_router.extract_entities(state["query"], context)
            state["entities_mentioned"] = entities
            
            # Load conversation history
            state["conversation_history"] = [
                {
                    "turn_id": turn.turn_id,
                    "query": turn.user_query,
                    "answer": turn.final_answer,
                    "entities": turn.entities_mentioned
                }
                for turn in self.memory.load_session(state["session_id"])[-3:]
            ]
            
            state["tools_used"].append("query_router")
            
            logger.info(f"Query routed as {query_type} with entities: {entities}")
            
        except Exception as e:
            logger.error(f"Query routing failed: {e}")
            state["error_message"] = f"Query routing failed: {str(e)}"
        
        return state
    
    def _route_decision(self, state: AgentState) -> str:
        """Decision function for conditional routing."""
        if state.get("error_message"):
            return "general"  # Fall back to general retrieval
        
        return state.get("query_type", "general")
    
    def _retrieve_schema_node(self, state: AgentState) -> AgentState:
        """Retrieve schema information using vector search only."""
        try:
            query = state["query"]
            
            # Use vector search to find relevant schema information
            results = self.vector_retriever.semantic_search(query, max_results=10)
            
            retrieved_context = [{
                "type": "vector_schema",
                "results": results
            }]
            
            state["retrieved_context"] = retrieved_context
            state["tools_used"].append("vector_retriever")
            
            logger.info(f"Vector schema retrieval completed: {len(results)} results")
            
        except Exception as e:
            logger.error(f"Vector schema retrieval failed: {e}")
            state["error_message"] = f"Vector schema retrieval failed: {str(e)}"
        
        return state
    
    def _generate_sql_node(self, state: AgentState) -> AgentState:
        """Generate SQL query for data analysis."""
        try:
            entities = state.get("entities_mentioned", {})
            all_tables = entities.get("tables", []) + entities.get("inherited_tables", [])
            
            if not all_tables:
                state["error_message"] = "No tables identified for data analysis"
                return state
            
            # Use first table for analysis
            table_name = all_tables[0]
            query = state["query"].lower()
            
            # Determine analysis type and generate appropriate SQL
            if "null" in query or "empty" in query:
                sql_info = self.sql_generator.generate_null_analysis_sql(table_name)
            else:
                # For other analysis types, fallback to null analysis for now
                sql_info = self.sql_generator.generate_null_analysis_sql(table_name)
            
            if "error" in sql_info:
                state["error_message"] = sql_info["error"]
                return state
            
            # Validate SQL safety
            safety_check = self.sql_generator.validate_sql_safety(sql_info["sql_query"])
            
            if not safety_check.get("safe", False):
                state["error_message"] = f"SQL safety check failed: {safety_check['reason']}"
                return state
            
            state["sql_query"] = sql_info["sql_query"]
            state["tools_used"].append("sql_generator")
            
            logger.info(f"SQL generated for {table_name}: {len(sql_info['sql_query'])} chars")
            
        except Exception as e:
            logger.error(f"SQL generation failed: {e}")
            state["error_message"] = f"SQL generation failed: {str(e)}"
        
        return state
    
    def _handle_conversation_node(self, state: AgentState) -> AgentState:
        """Handle conversational interactions using LLM for dynamic responses."""
        try:
            query = state["query"]
            conversation_history = state.get("conversation_history", [])
            
            # Use LLM to generate contextual conversation responses
            conversation_prompt = f"""You are an AML (Anti-Money Laundering) database assistant. Respond to the user's conversational query naturally and helpfully.

User Query: "{query}"

Context: This is a conversational interaction. The user may be greeting you, asking for help, or having a general conversation.

Previous conversation context: {conversation_history[-2:] if conversation_history else "None"}

Generate a friendly, informative response that:
- Acknowledges their query appropriately
- Briefly explains your AML database analysis capabilities if relevant
- Offers specific examples of what you can help with
- Invites them to ask a specific question
- Maintains context from previous conversation if applicable

Keep the response concise but helpful (2-4 sentences max)."""

            try:
                # Convert to message format for LLM
                messages = [{"role": "user", "content": conversation_prompt}]
                llm_response = self.llm_provider.chat(messages)
                response = llm_response.content if hasattr(llm_response, 'content') else str(llm_response)
                
                logger.info(f"LLM generated conversation response for: {query[:50]}...")
                
            except Exception as llm_error:
                logger.error(f"LLM conversation failed: {llm_error}, using fallback")
                response = "Hello! I'm your AML database assistant. I can help you explore database schemas, analyze data patterns, and answer questions about your AML system. What would you like to explore?"
            
            state["final_answer"] = response
            state["confidence_score"] = 1.0  # High confidence for conversational responses
            state["tools_used"].append("llm_conversation_agent")
            
            logger.info("Handled conversational query with LLM-generated response")
            
        except Exception as e:
            logger.error(f"Conversation handling failed: {e}")
            state["final_answer"] = "I'm here to help! What would you like to know about your AML database?"
            state["confidence_score"] = 0.8
        
        return state
    
    def _execute_sql_node(self, state: AgentState) -> AgentState:
        """Execute the generated SQL query."""
        try:
            sql_query = state.get("sql_query")
            if not sql_query:
                state["error_message"] = "No SQL query to execute"
                return state
            
            # Execute SQL
            sql_results = self.sql_executor.execute_query(sql_query, max_rows=1000)
            state["sql_results"] = sql_results
            state["tools_used"].append("sql_executor")
            
            if sql_results.get("success"):
                logger.info(f"SQL executed successfully: {sql_results.get('rows_returned', 0)} rows")
            else:
                logger.warning(f"SQL execution failed: {sql_results.get('error')}")
            
        except Exception as e:
            logger.error(f"SQL execution failed: {e}")
            state["error_message"] = f"SQL execution failed: {str(e)}"
        
        return state
    
    def _retrieve_general_node(self, state: AgentState) -> AgentState:
        """Retrieve general information using vector search only."""
        try:
            # Use vector-only semantic search
            results = self.vector_retriever.semantic_search(state["query"], max_results=15)
            
            state["retrieved_context"] = [{
                "type": "general_vector",
                "results": results
            }]
            state["tools_used"].append("vector_retriever")
            
            logger.info(f"Vector general retrieval completed: {len(results)} results")
            
        except Exception as e:
            logger.error(f"Vector general retrieval failed: {e}")
            state["error_message"] = f"Vector general retrieval failed: {str(e)}"
        
        return state
    
    def _compose_answer_node(self, state: AgentState) -> AgentState:
        """Compose the final answer based on retrieved information."""
        try:
            query = state["query"]
            query_type = state.get("query_type", "general")
            
            # Choose composition strategy based on query type
            if query_type in ["schema", "follow_up"]:
                # Find schema information
                schema_context = None
                for context in state.get("retrieved_context", []):
                    if context.get("type") == "schema" and context.get("schema_info"):
                        schema_context = context["schema_info"]
                        break
                
                if schema_context:
                    answer_info = self.answer_composer.compose_schema_answer(query, schema_context)
                else:
                    # Fallback to general composition
                    answer_info = self._compose_general_answer(query, state.get("retrieved_context", []))
                    
            elif query_type == "data_analysis":
                sql_results = state.get("sql_results", {})
                answer_info = self.answer_composer.compose_data_analysis_answer(query, sql_results)
                
            else:
                answer_info = self._compose_general_answer(query, state.get("retrieved_context", []))
            
            state["final_answer"] = answer_info.get("answer", "I couldn't generate an answer.")
            state["confidence_score"] = answer_info.get("confidence_score", 0.0)
            
            logger.info(f"Answer composed with confidence {state['confidence_score']:.2f}")
            
        except Exception as e:
            logger.error(f"Answer composition failed: {e}")
            state["final_answer"] = f"I encountered an error while composing the answer: {str(e)}"
            state["confidence_score"] = 0.0
        
        return state
    
    def _compose_general_answer(self, query: str, retrieved_context: List[Dict]) -> Dict[str, Any]:
        """Compose answer for general queries using LLM with vector search results."""
        if not retrieved_context:
            return {
                "answer": "I couldn't find relevant information to answer your query.",
                "confidence_score": 0.0,
                "grounded": False
            }
        
        # Extract results from context
        all_results = []
        for context in retrieved_context:
            if "results" in context:
                all_results.extend(context["results"])
        
        if not all_results:
            return {
                "answer": "No relevant information found in the database.",
                "confidence_score": 0.1,
                "grounded": False
            }
        
        # Use LLM to compose answer from vector search results
        try:
            # Prepare context from top results
            context_parts = []
            for i, result in enumerate(all_results[:5], 1):
                content = result.get("content", "")
                similarity = result.get("similarity_score", 0.0)
                collection = result.get("collection", "unknown")
                metadata = result.get("metadata", {})
                
                context_parts.append(f"Result {i} (Similarity: {similarity:.3f}, Source: {collection}):")
                context_parts.append(f"Content: {content}")
                if metadata:
                    context_parts.append(f"Metadata: {metadata}")
                context_parts.append("")
            
            context_text = "\n".join(context_parts)
            
            answer_prompt = f"""Based on the following database search results, provide a comprehensive answer to the user's question.

User Question: "{query}"

Search Results:
{context_text}

Instructions:
- Synthesize information from the search results to answer the question
- Focus on the most relevant and high-similarity results
- If the results contain database schema information, explain it clearly
- If the results contain AML/financial data, provide context about its purpose
- Be specific and cite which sources support your answer
- If the information is insufficient, say so honestly
- Keep the response helpful and focused on the user's question

Generate a clear, informative response:"""

            # Convert to message format for LLM
            messages = [{"role": "user", "content": answer_prompt}]
            llm_response = self.llm_provider.chat(messages)
            answer = llm_response.content if hasattr(llm_response, 'content') else str(llm_response)
            
            # Calculate confidence based on result quality
            avg_similarity = sum(r.get("similarity_score", 0) for r in all_results[:5]) / min(5, len(all_results))
            confidence = min(0.9, avg_similarity * 1.2)  # Scale similarity to confidence
            
            return {
                "answer": answer,
                "confidence_score": confidence,
                "grounded": True,
                "sources": [{"type": "vector_search", "count": len(all_results), "collections": list(set(r.get("collection", "") for r in all_results))}]
            }
            
        except Exception as e:
            logger.error(f"LLM answer composition failed: {e}")
            # Fallback to simple composition
            answer_parts = ["Based on the database search results:"]
            
            for i, result in enumerate(all_results[:3], 1):
                content = result.get("content", "")[:200]
                similarity = result.get("similarity_score", 0.0)
                collection = result.get("collection", "unknown")
                
                answer_parts.append(f"{i}. From {collection} (similarity: {similarity:.3f}): {content}")
            
            if len(all_results) > 3:
                answer_parts.append(f"... and {len(all_results) - 3} more results")
            
            return {
                "answer": "\n".join(answer_parts),
                "confidence_score": min(0.6, len(all_results) * 0.1),
                "grounded": True,
                "sources": [{"type": "vector_search_fallback", "count": len(all_results)}]
            }
            answer_parts.append(f"... and {len(all_results) - 5} more results")
        
        return {
            "answer": "\n".join(answer_parts),
            "confidence_score": min(0.8, len(all_results) * 0.1),
            "grounded": True,
            "sources": [{"type": "schema_search", "count": len(all_results)}]
        }
    
    def _save_memory_node(self, state: AgentState) -> AgentState:
        """Save the conversation turn to memory."""
        try:
            turn = ConversationTurn(
                turn_id=state["turn_id"],
                user_query=state["query"],
                query_type=state.get("query_type", "general"),
                entities_mentioned=state.get("entities_mentioned", {}),
                tools_used=state.get("tools_used", []),
                final_answer=state.get("final_answer", ""),
                confidence_score=state.get("confidence_score", 0.0),
                timestamp=datetime.utcnow().isoformat()
            )
            
            self.memory.save_turn(state["session_id"], turn)
            
            logger.info(f"Conversation turn saved: {state['turn_id']}")
            
        except Exception as e:
            logger.error(f"Memory save failed: {e}")
            # Don't fail the whole process for memory issues
        
        return state
    
    def process_query(self, 
                     query: str, 
                     session_id: str = None, 
                     turn_id: str = None) -> Dict[str, Any]:
        """
        Process a user query through the complete agent workflow.
        
        Args:
            query: User's question
            session_id: Session identifier for conversation continuity
            turn_id: Turn identifier for this specific interaction
        
        Returns:
            Dict containing the response and metadata
        """
        # Generate IDs if not provided
        if not session_id:
            session_id = str(uuid.uuid4())
        if not turn_id:
            turn_id = str(uuid.uuid4())
        
        # Initial state
        initial_state = AgentState(
            query=query,
            query_type="general",  # Will be determined by routing
            session_id=session_id,
            turn_id=turn_id,
            conversation_history=[],
            retrieved_context=[],
            sql_query=None,
            sql_results=None,
            entities_mentioned={},
            final_answer=None,
            confidence_score=0.0,
            tools_used=[],
            error_message=None
        )
        
        try:
            # Run the graph
            config = {"configurable": {"thread_id": session_id}}
            result = self.graph.invoke(initial_state, config)
            
            # Prepare response
            response = {
                "answer": result.get("final_answer", "I couldn't process your query."),
                "confidence_score": result.get("confidence_score", 0.0),
                "query_type": result.get("query_type", "general"),
                "tools_used": result.get("tools_used", []),
                "session_id": session_id,
                "turn_id": turn_id,
                "entities_mentioned": result.get("entities_mentioned", {}),
                "timestamp": datetime.utcnow().isoformat()
            }
            
            # Add debug info if there was an error
            if result.get("error_message"):
                response["error"] = result["error_message"]
                response["debug_info"] = {
                    "sql_query": result.get("sql_query"),
                    "retrieved_context_count": len(result.get("retrieved_context", []))
                }
            
            logger.info(f"Query processed successfully: {query[:50]}...")
            return response
            
        except Exception as e:
            logger.error(f"Agent processing failed: {e}")
            return {
                "answer": f"I encountered an error while processing your query: {str(e)}",
                "confidence_score": 0.0,
                "query_type": "error",
                "tools_used": [],
                "session_id": session_id,
                "turn_id": turn_id,
                "error": str(e),
                "timestamp": datetime.utcnow().isoformat()
            }