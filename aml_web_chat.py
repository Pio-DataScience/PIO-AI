
"""
Web Chat Interface for AML Database with Production Agentic RAG System
Enhanced with structured observability, performance optimization, and agentic behavior.
"""

import sys
import os
import uuid
import uvicorn
import chromadb
from pathlib import Path
import traceback
import time
import logging
from typing import List, Dict, Any, Optional
from datetime import datetime
import asyncio

# Add package to path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

try:
    from fastapi import FastAPI, HTTPException, Request, BackgroundTasks
    from fastapi.staticfiles import StaticFiles
    from fastapi.responses import HTMLResponse, JSONResponse
    from pydantic import BaseModel
    import chromadb
    from chromadb.config import Settings
    from sentence_transformers import SentenceTransformer
    
    # Core services
    from services.llm.provider import get_available_providers, llm_manager
    from services.db.catalog_store import CatalogStore
    
    # Enhanced production services
    from services.observability import (
        ObservabilityManager, ComponentType, StructuredLogger
    )
    from services.performance import PerformanceOptimizer
    from services.agents import (
        AgentOrchestrator, LANGGRAPH_AVAILABLE
    )
    # Modern agentic components
    from services.agents.modern_orchestrator import ModernAgentOrchestrator
    from services.agents.observability import get_observability
    from services.storage.parquet_layer import ParquetDataLayer
    from services.ingest.dictionary_ingester import OracleDictionaryIngester as DictionaryIngester
    
    # Enhanced retrieval with query reformulation
    from services.retriever.enhanced_semantic_search import EnhancedSemanticSearch
    from services.agents.query_reformulator import IntelligentQueryReformulator
    
    print("Production-ready packages imported successfully")
    print(f"LangGraph Agent Support: {LANGGRAPH_AVAILABLE}")
    
except ImportError as e:
    print(f"Import error: {e}")
    print("📝 Some production features may be unavailable")
    # Fallback for basic functionality
    from fastapi import FastAPI, HTTPException, Request
    from fastapi.staticfiles import StaticFiles
    from fastapi.responses import HTMLResponse, JSONResponse
    from pydantic import BaseModel

# Enhanced Pydantic models
class ChatMessage(BaseModel):
    message: str
    max_results: int = 5
    session_id: Optional[str] = None
    user_id: Optional[str] = None

class ChatResponse(BaseModel):
    response: str
    search_results: List[Dict[str, Any]]
    timestamp: str
    processing_time: float
    session_id: str
    turn_id: str
    query_type: str
    tools_used: List[str]
    confidence_score: float

class SystemStatus(BaseModel):
    status: str
    timestamp: str
    components: Dict[str, str]
    performance_stats: Dict[str, Any]
    agent_available: bool
    storage_layer: str

# Initialize chatbot on startup using lifespan
from contextlib import asynccontextmanager

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    global chatbot
    # Create without auto-initialization to avoid double initialization
    chatbot = AMLWebChatBot(auto_initialize=False)
    chatbot.initialize()
    yield
    # Shutdown (if needed)
    pass

# Initialize FastAPI app with enhanced configuration
app = FastAPI(
    title="PIO AI - Production Agentic RAG System",
    description="Production-ready agentic company assistant with comprehensive observability",
    version="2.0.0",
    docs_url="/api/docs",
    redoc_url="/api/redoc",
    lifespan=lifespan
)

# Configure detailed audit logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
audit_logger = logging.getLogger('AML_AUDIT')

# Global chat bot instance
chatbot = None

class SystemAudit:
    """Audit tracking for system phases."""
    
    def __init__(self):
        self.phase_times = {}
        self.phase_success = {}
        self.phase_details = {}
        
    def start_phase(self, phase_name: str):
        """Start timing a system phase."""
        self.phase_times[phase_name] = {'start': time.time()}
        audit_logger.info(f"🔄 Starting {phase_name}")
        
    def end_phase(self, phase_name: str, success: bool = True, details: str = ""):
        """End timing a system phase."""
        if phase_name in self.phase_times:
            duration = time.time() - self.phase_times[phase_name]['start']
            self.phase_times[phase_name]['duration'] = duration
            self.phase_success[phase_name] = success
            self.phase_details[phase_name] = details
            
            status = "SUCCESS" if success else "FAILED"
            audit_logger.info(f"{status} {phase_name} completed in {duration:.3f}s - {details}")
        
    def get_audit_summary(self) -> Dict[str, Any]:
        """Get comprehensive audit summary."""
        return {
            'phases': self.phase_times,
            'success_rates': self.phase_success,
            'details': self.phase_details,
            'total_time': sum(p.get('duration', 0) for p in self.phase_times.values())
        }

class AMLWebChatBot:
    """Production-ready web-based chat interface with agentic behavior."""
    
    def __init__(self, auto_initialize: bool = True):
        self.bge_model = None
        self.chroma_client = None
        self.catalog_store = None
        self.collections = {}
        self.embedding_dimension = None
        
        # Production components
        self.observability = None
        self.performance_optimizer = None
        self.agent_orchestrator = None
        self.modern_orchestrator = None  # Explicitly initialize to None
        self.parquet_layer = None
        self.dictionary_ingester = None
        self.logger = None
        
        # Enhanced retrieval components
        self.enhanced_search = None  # EnhancedSemanticSearch instance
        self.query_reformulator = None  # Standalone reformulator if needed
        
        # Initialize LLM manager safely
        try:
            from services.llm.provider import LLMManager
            self.llm_manager = LLMManager()
            print("LLM Manager initialized")
        except Exception as e:
            print(f"Warning: LLM Manager initialization failed: {e}")
            self.llm_manager = None
        
        self.audit = SystemAudit()
        
        # Auto-initialize if requested (default: True)
        if auto_initialize:
            try:
                self.initialize()
            except Exception as e:
                print(f"Auto-initialization failed: {e}")
                print("System will run with limited functionality")
    
    def _initialize_production_components(self):
        """Initialize production-ready components."""
        try:
            # Initialize observability
            self.audit.start_phase("OBSERVABILITY_INIT")
            base_path = Path(__file__).parent / "data" / "observability"
            self.observability = ObservabilityManager(
                base_path=base_path,
                enable_tracing=True,
                enable_metrics=True
            )
            self.logger = self.observability.get_logger(ComponentType.API)
            self.audit.end_phase("OBSERVABILITY_INIT", True, "Structured logging enabled")
            
            # Initialize performance optimizer
            self.audit.start_phase("PERFORMANCE_INIT")
            cache_config = {
                "use_redis": False,  # Start with memory cache
                "memory_cache_size": 10000,
                "default_ttl": 3600
            }
            self.performance_optimizer = PerformanceOptimizer(cache_config=cache_config)
            self.audit.end_phase("PERFORMANCE_INIT", True, "Cache and optimization enabled")
            
            # Initialize storage layer
            self.audit.start_phase("STORAGE_LAYER_INIT")
            data_path = Path(__file__).parent / "data" / "parquet"
            self.parquet_layer = ParquetDataLayer(base_path=data_path)
            self.audit.end_phase("STORAGE_LAYER_INIT", True, "Parquet storage layer ready")
            
            print("Production components initialized successfully")
            
        except Exception as e:
            print(f"Production components initialization partially failed: {e}")
            # Continue with basic functionality
        
    def initialize(self):
        """Initialize all components with production enhancements."""
        print("Initializing Production Agentic RAG System...")
        
        # Initialize production components first
        self._initialize_production_components()
        
        # Initialize BGE model with performance tracking
        self.audit.start_phase("BGE_MODEL_LOADING")
        try:
            print("Loading BGE-large-en-v1.5 model...")
            self.bge_model = SentenceTransformer('BAAI/bge-large-en-v1.5')
            self.embedding_dimension = self.bge_model.get_sentence_embedding_dimension()
            self.audit.end_phase("BGE_MODEL_LOADING", True, f"Dimension: {self.embedding_dimension}")
            
            if self.logger:
                self.logger.info("bge_model_load", f"BGE model loaded successfully", 
                               metadata={"dimension": self.embedding_dimension})
            print(f"BGE model loaded (dimension: {self.embedding_dimension})")
            
        except Exception as e:
            self.audit.end_phase("BGE_MODEL_LOADING", False, str(e))
            if self.logger:
                self.logger.error("bge_model_load", f"BGE model loading failed: {e}")
            raise
        
        # Initialize ChromaDB with enhanced error handling
        self.audit.start_phase("CHROMADB_INIT")
        try:
            warehouse_path = Path(__file__).parent / "warehouse"
            chroma_path = warehouse_path / "vectors"
            
            self.chroma_client = chromadb.PersistentClient(
                path=str(chroma_path),
                settings=Settings(
                    anonymized_telemetry=False,
                    allow_reset=True
                )
            )
            self.audit.end_phase("CHROMADB_INIT", True, f"Path: {chroma_path}")
        except Exception as e:
            self.audit.end_phase("CHROMADB_INIT", False, str(e))
            raise
        
        # Load collections with dimension validation
        self.audit.start_phase("COLLECTION_LOADING")
        collections = self.chroma_client.list_collections()
        collection_details = []
        dimension_issues = []
        
        for collection in collections:
            try:
                coll = self.chroma_client.get_collection(collection.name)
                count = coll.count()
                
                if count > 0:
                    # Check embedding dimension if collection has data
                    dimension_info = "unknown"
                    try:
                        sample = coll.get(limit=1, include=['embeddings'])
                        if sample['embeddings']:
                            coll_dimension = len(sample['embeddings'][0])
                            dimension_info = f"{coll_dimension}D"
                            
                            # Check for dimension mismatch
                            if coll_dimension != self.embedding_dimension:
                                issue_msg = f"Collection {collection.name}: {coll_dimension}D vs BGE {self.embedding_dimension}D"
                                dimension_issues.append(issue_msg)
                                audit_logger.warning(f"⚠️ DIMENSION MISMATCH: {issue_msg}")
                    except Exception as dim_e:
                        dimension_info = f"error: {dim_e}"
                    
                    self.collections[collection.name] = coll
                    collection_details.append(f"{collection.name}({count} docs, {dimension_info})")
                    print(f"Loaded collection '{collection.name}' with {count} embeddings ({dimension_info})")
                
            except Exception as e:
                audit_logger.error(f"Error loading collection {collection.name}: {e}")
                
        if dimension_issues:
            self.audit.end_phase("COLLECTION_LOADING", False, f"Dimension mismatches: {'; '.join(dimension_issues)}")
            print("\nCRITICAL: Dimension mismatches detected!")
            print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
            for issue in dimension_issues:
                print(f"{issue}")
            print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
            print("\n🔧 SOLUTION: Run the dimension fix script:")
            print("   .venv\\Scripts\\python.exe scripts\\53_fix_embedding_dimensions.py")
            print("\nWARNING: Semantic search will fail until dimensions are aligned!")
        else:
            self.audit.end_phase("COLLECTION_LOADING", True, f"Loaded {len(self.collections)} collections: {', '.join(collection_details)}")
            print("\n All collections have compatible embedding dimensions!")
        
        # Add detailed system diagnostics
        self.audit.start_phase("SYSTEM_DIAGNOSTICS")
        print("\nSystem Diagnostics Summary:")
        print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
        print(f"BGE Model: {self.embedding_dimension}D embeddings")
        print(f"Collections: {len(self.collections)} loaded")
        for name, details in zip(self.collections.keys(), collection_details):
            print(f"   • {details}")
        print(f"Semantic Search: {'Ready' if not dimension_issues else 'BLOCKED by dimension mismatch'}")
        print(f"LLM Provider: {'Available' if self.llm_manager else 'Not available'}")
        
        # Production components status
        if hasattr(self, 'observability') and self.observability:
            print(f"Observability: Enabled")
        if hasattr(self, 'performance_optimizer') and self.performance_optimizer:
            print(f"Performance Optimization: Enabled")
        if hasattr(self, 'parquet_layer') and self.parquet_layer:
            print(f"Parquet Storage: Ready")
        
        print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
        self.audit.end_phase("SYSTEM_DIAGNOSTICS", True, f"Collections: {len(self.collections)}, Dimension issues: {len(dimension_issues)}")
        
        # Initialize modern agentic orchestrator
        if LANGGRAPH_AVAILABLE and self.performance_optimizer:
            self.audit.start_phase("AGENT_INIT")
            try:
                # Set up observability
                logger, tracer = get_observability()
                
                # Configure modern orchestrator
                modern_config = {
                    "llm": {
                        "provider": "cohere",  # Use available provider
                        "model": "command-r-08-2024",
                        "temperature": 0.1
                    },
                    "memory_path": "memory",
                    "schema_db_path": "indexes/graph/AI_AML.sqlite",
                    "db_config": self._get_oracle_config() or {}
                }
                
                # Initialize modern orchestrator with shared resources for performance
                try:
                    self.modern_orchestrator = ModernAgentOrchestrator(
                        modern_config,
                        shared_bge_model=self.bge_model,  # Reuse pre-loaded BGE model
                        shared_chroma_client=self.chroma_client  # Reuse ChromaDB client
                    )
                    print("Modern orchestrator initialized successfully (with shared BGE model)")
                except Exception as orchestrator_error:
                    print(f"Modern orchestrator failed: {orchestrator_error}")
                    print(f"Orchestrator traceback: {traceback.format_exc()}")
                    self.modern_orchestrator = None
                
                # Keep legacy orchestrator as fallback
                oracle_config = self._get_oracle_config()
                if oracle_config:
                    self.agent_orchestrator = AgentOrchestrator(
                        retriever=self,  # Use self as retriever
                        llm_provider=self.llm_manager,
                        oracle_dsn=oracle_config['dsn'],
                        oracle_user=oracle_config['user'],
                        oracle_password=oracle_config['password']
                    )
                
                print("Modern agentic orchestrator initialized")
                print("Legacy agent orchestrator available as fallback")
                self.audit.end_phase("AGENT_INIT", True, "Modern orchestrator ready")
                
            except Exception as e:
                print(f"Warning: Modern agent initialization failed: {e}")
                print(f"Traceback: {traceback.format_exc()}")
                self.audit.end_phase("AGENT_INIT", False, str(e))
                # Fallback to legacy if available
                self.modern_orchestrator = None
        
        # Prioritize the BGE-compatible dictionary metadata collection
        primary_collection_name = None
        if 'aml_dictionary_metadata_bge' in self.collections:
            print("🎯 Using BGE-compatible dictionary metadata as primary source")
            # Move it to the front for priority searching
            primary_collection = self.collections.pop('aml_dictionary_metadata_bge')
            self.collections = {'aml_dictionary_metadata_bge': primary_collection, **self.collections}
            primary_collection_name = 'aml_dictionary_metadata_bge'
        elif 'aml_dictionary_metadata' in self.collections:
            print("Warning: Using legacy dictionary metadata (dimension mismatch expected)")
            # Move it to the front for priority searching
            primary_collection = self.collections.pop('aml_dictionary_metadata')
            self.collections = {'aml_dictionary_metadata': primary_collection, **self.collections}
            primary_collection_name = 'aml_dictionary_metadata'
        elif 'aml_catalog' in self.collections:
            primary_collection_name = 'aml_catalog'
        
        # Initialize enhanced semantic search with query reformulation
        if primary_collection_name and self.bge_model and self.chroma_client and not dimension_issues:
            self.audit.start_phase("ENHANCED_SEARCH_INIT")
            try:
                self.enhanced_search = EnhancedSemanticSearch(
                    chroma_client=self.chroma_client,
                    bge_model=self.bge_model,
                    collection_name=primary_collection_name
                )
                print(f"🧠 Enhanced semantic search initialized with query reformulation")
                print(f"   Primary collection: {primary_collection_name}")
                print(f"   Features: Intent detection, complete metadata retrieval, conversation context")
                self.audit.end_phase("ENHANCED_SEARCH_INIT", True, f"Collection: {primary_collection_name}")
            except Exception as e:
                print(f"Warning: Enhanced search initialization failed: {e}")
                print(f"Falling back to standard semantic search")
                self.enhanced_search = None
                self.audit.end_phase("ENHANCED_SEARCH_INIT", False, str(e))
        else:
            print("ℹ️ Enhanced search disabled (dimension issues or missing components)")
            self.enhanced_search = None
        
        # Initialize catalog store
        catalog_db_path = warehouse_path / "catalog.db"
        self.catalog_store = CatalogStore(str(catalog_db_path))
        
        print("Production Agentic RAG System initialized successfully!")
    
    def _get_oracle_config(self) -> Optional[Dict[str, str]]:
        """Get Oracle database configuration from environment or config files."""
        try:
            # Try environment variables first
            import os
            oracle_dsn = os.getenv("ORACLE_DSN")
            oracle_user = os.getenv("ORACLE_USER") 
            oracle_password = os.getenv("ORACLE_PASSWORD")
            
            if all([oracle_dsn, oracle_user, oracle_password]):
                return {
                    "dsn": oracle_dsn,
                    "user": oracle_user,
                    "password": oracle_password
                }
            
            # Try config file
            config_path = Path(__file__).parent / "config" / "secrets.env"
            if config_path.exists():
                with open(config_path, 'r') as f:
                    for line in f:
                        if line.strip() and not line.startswith('#'):
                            key, value = line.strip().split('=', 1)
                            os.environ[key] = value.strip('"')
                
                oracle_dsn = os.getenv("ORACLE_DSN")
                oracle_user = os.getenv("ORACLE_USER")
                oracle_password = os.getenv("ORACLE_PASSWORD")
                
                if all([oracle_dsn, oracle_user, oracle_password]):
                    return {
                        "dsn": oracle_dsn,
                        "user": oracle_user,
                        "password": oracle_password
                    }
            
            return None
            
        except Exception as e:
            print(f"⚠️ Failed to load Oracle config: {e}")
            return None
        
    def semantic_search(self, query: str, max_results: int = 5, session_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Perform intelligent semantic search with query reformulation.
        
        Uses enhanced search when available for:
        - Query reformulation and intent detection
        - Complete metadata retrieval (all columns, not just top-K)
        - Conversation context tracking for follow-up questions
        
        Falls back to standard search if enhanced search unavailable.
        """
        if self.logger:
            with self.logger.trace_operation("semantic_search", metadata={"query": query[:50], "max_results": max_results}) as perf:
                return self._perform_semantic_search(query, max_results, session_id, perf)
        else:
            return self._perform_semantic_search(query, max_results, session_id)
    
    def _perform_semantic_search(self, query: str, max_results: int = 5, session_id: Optional[str] = None, perf=None) -> List[Dict[str, Any]]:
        """
        Internal semantic search implementation.
        Routes to enhanced search when available, falls back to standard search.
        """
        # Try enhanced search first (with query reformulation)
        if self.enhanced_search:
            try:
                if self.logger:
                    self.logger.info("semantic_search", "Using enhanced search with query reformulation")
                
                # Perform enhanced search
                results, retrieval_query = self.enhanced_search.search(
                    query=query,
                    max_results=max_results,
                    session_id=session_id
                )
                
                if perf:
                    perf.checkpoint("enhanced_search_completed")
                
                # Log query reformulation details
                if self.logger:
                    self.logger.info(
                        "query_reformulation",
                        f"Original: '{query[:50]}...' -> Reformulated: '{retrieval_query.reformulated_query[:50]}...'",
                        metadata={
                            "intent": retrieval_query.intent.value,
                            "table": retrieval_query.target_table,
                            "complete_metadata": retrieval_query.should_retrieve_complete_metadata,
                            "confidence": retrieval_query.confidence
                        }
                    )
                
                # Convert to standard format
                formatted_results = []
                for result in results:
                    formatted_results.append({
                        "content": result.get('document', ''),
                        "similarity": 1.0 - result.get('distance', 0.0),
                        "collection": self.enhanced_search.collection_name,
                        "metadata": result.get('metadata', {}),
                        "intent": retrieval_query.intent.value,
                        "reformulated_query": retrieval_query.reformulated_query
                    })
                
                if self.logger:
                    self.logger.info("semantic_search", f"Enhanced search returned {len(formatted_results)} results")
                
                return formatted_results
                
            except Exception as e:
                if self.logger:
                    self.logger.error("enhanced_search", f"Enhanced search failed: {e}, falling back to standard search")
                print(f"Warning: Enhanced search failed: {e}")
                # Fall through to standard search
        
        # Standard search fallback
        all_results = []
        search_details = []
        
        if not self.bge_model or not self.collections:
            if self.logger:
                self.logger.warning("semantic_search", "Missing model or collections")
            return []
        
        if self.logger:
            self.logger.info("semantic_search", "Using standard search (no query reformulation)")
        
        # Generate BGE embedding for query with caching
        cache_manager = self.performance_optimizer.get_cache_manager() if self.performance_optimizer else None
        cache_key = f"embedding:{hash(query)}"
        
        query_embedding = None
        if cache_manager:
            query_embedding = cache_manager.get(cache_key)
        
        if query_embedding is None:
            try:
                query_embedding = self.bge_model.encode([query])[0].tolist()
                if cache_manager:
                    cache_manager.set(cache_key, query_embedding, ttl=1800)  # Cache for 30 minutes
                if perf:
                    perf.checkpoint("embedding_generated")
            except Exception as e:
                if self.logger:
                    self.logger.error("embedding_generation", f"Failed to generate embedding: {e}")
                return []
        
        # Search in all collections
        for collection_name, collection in self.collections.items():
            try:
                search_results = collection.query(
                    query_embeddings=[query_embedding],
                    n_results=max_results
                )
                
                result_count = 0
                if search_results['documents'] and search_results['documents'][0]:
                    result_count = len(search_results['documents'][0])
                    for doc, distance, metadata in zip(
                        search_results['documents'][0],
                        search_results['distances'][0],
                        search_results['metadatas'][0] or [{}] * result_count
                    ):
                        similarity = 1.0 - distance
                        all_results.append({
                            "content": doc,
                            "similarity": similarity,
                            "collection": collection_name,
                            "metadata": metadata or {}
                        })
                
                search_details.append(f"{collection_name}:{result_count}")
                
                if perf:
                    perf.checkpoint(f"searched_{collection_name}")
                
            except Exception as e:
                if self.logger:
                    self.logger.error("collection_search", f"Error searching {collection_name}: {e}")
                search_details.append(f"{collection_name}:ERROR")
        
        # Sort by similarity and return top results
        final_results = sorted(all_results, key=lambda x: x['similarity'], reverse=True)[:max_results]
        
        if self.logger:
            self.logger.info("semantic_search", f"Search completed",
                           metadata={"collections_searched": len(search_details), "final_results": len(final_results)})
        
        return final_results
    
    async def process_chat_message(self, message: str, session_id: str = None, user_id: str = None) -> Dict[str, Any]:
        """Process chat message with modern agentic orchestrator."""
        start_time = time.time()
        session_id = session_id or str(uuid.uuid4())
        turn_id = str(uuid.uuid4())
        
        try:
            # DEBUG: Check what orchestrators are available
            has_modern = hasattr(self, 'modern_orchestrator') and self.modern_orchestrator
            has_legacy = hasattr(self, 'agent_orchestrator') and self.agent_orchestrator
            print(f"DEBUG - Modern orchestrator available: {has_modern}")
            print(f"DEBUG - Legacy orchestrator available: {has_legacy}")
            
            # Prioritize modern orchestrator
            if has_modern:
                print("Using modern agentic orchestrator")
                if self.logger:
                    self.logger.info("chat_processing", "Using modern agentic orchestrator",
                                   session_id=session_id, turn_id=turn_id)
                
                # Set observability context
                logger, tracer = get_observability()
                logger.set_trace_context(turn_id, session_id)
                
                response = await self.modern_orchestrator.process_query(
                    query=message,
                    session_id=session_id
                )
                
                processing_time = (time.time() - start_time) * 1000
                
                return ChatResponse(
                    response=response.get("response", "I couldn't process your query."),
                    search_results=[],  # Modern orchestrator handles internally
                    timestamp=datetime.utcnow().isoformat(),
                    processing_time=processing_time,
                    session_id=session_id,
                    turn_id=turn_id,
                    query_type=response.get("intent", "general"),
                    tools_used=response.get("tools_used", []),
                    confidence_score=response.get("confidence", 0.0)
                ).model_dump()
            
            # Fallback to legacy agentic system
            elif has_legacy:
                print("Using legacy agentic orchestrator")
                if self.logger:
                    self.logger.info("chat_processing", "Using legacy agentic orchestrator", 
                                   session_id=session_id, turn_id=turn_id)
                
                response = self.agent_orchestrator.process_query(
                    query=message,
                    session_id=session_id,
                    turn_id=turn_id
                )
                
                processing_time = (time.time() - start_time) * 1000
                
                # Extract search results from agent response
                search_results = []
                if hasattr(self, '_last_search_results'):
                    search_results = self._last_search_results
                
                return ChatResponse(
                    response=response.get("answer", "I couldn't process your query."),
                    search_results=search_results,
                    timestamp=datetime.utcnow().isoformat(),
                    processing_time=processing_time,
                    session_id=session_id,
                    turn_id=turn_id,
                    query_type=response.get("query_type", "general"),
                    tools_used=response.get("tools_used", []),
                    confidence_score=response.get("confidence_score", 0.0)
                ).model_dump()
            
            else:
                # Final fallback to traditional processing
                print("⚠️ Falling back to traditional chat processing")
                return await self._process_traditional_chat(message, session_id, turn_id, user_id, start_time)
                
        except Exception as e:
            processing_time = (time.time() - start_time) * 1000
            
            if self.logger:
                self.logger.error("chat_processing", f"Chat processing failed: {e}",
                                session_id=session_id, turn_id=turn_id)
            
            # Try traditional fallback on error
            try:
                return await self._process_traditional_chat(message, session_id, turn_id, user_id, start_time)
            except:
                # Ultimate fallback
                return ChatResponse(
                    response=f"I encountered an error while processing your message. Please try rephrasing your question or ask about specific database tables.",
                    search_results=[],
                    timestamp=datetime.utcnow().isoformat(),
                    processing_time=processing_time,
                    session_id=session_id,
                    turn_id=turn_id,
                    query_type="error",
                    tools_used=[],
                    confidence_score=0.0
                ).model_dump()
    
    async def _process_traditional_chat(self, message: str, session_id: str, turn_id: str, user_id: str, start_time: float) -> Dict[str, Any]:
        """Traditional chat processing without agent orchestrator."""
        if self.logger:
            with self.logger.trace_operation("traditional_chat", session_id=session_id, turn_id=turn_id) as perf:
                return self._execute_traditional_chat(message, session_id, turn_id, user_id, start_time, perf)
        else:
            return self._execute_traditional_chat(message, session_id, turn_id, user_id, start_time)
    
    def _execute_traditional_chat(self, message: str, session_id: str, turn_id: str, user_id: str, start_time: float, perf=None) -> Dict[str, Any]:
        """Execute traditional chat processing with conversation detection."""
        # Import QueryRouter for conversation detection
        from services.agents.agentic_behavior import QueryRouter
        router = QueryRouter()
        
        # Check if this is casual conversation
        query_type = router.classify_query(message, {})
        
        if query_type == "conversation":
            # Handle conversation without database search
            conversation_response = self._handle_casual_conversation(message)
            processing_time = (time.time() - start_time) * 1000
            
            return ChatResponse(
                response=conversation_response,
                search_results=[],
                timestamp=datetime.utcnow().isoformat(),
                processing_time=processing_time,
                session_id=session_id,
                turn_id=turn_id,
                query_type="conversation",
                tools_used=["conversation_handler"],
                confidence_score=1.0
            ).model_dump()
        
        # Otherwise, perform database search and processing with session context
        search_results = self.semantic_search(message, max_results=5, session_id=session_id)
        self._last_search_results = search_results  # Store for potential agent use
        
        if perf:
            perf.checkpoint("search_completed")
        
        # Build context and generate response
        context = self.build_context(message, max_results=5)
        
        if perf:
            perf.checkpoint("context_built")
        
        # Generate LLM response
        llm_response = "Based on the database search results, I found relevant information about your query."
        if self.llm_manager:
            try:
                llm_response = self.llm_manager.generate_response(
                    query=message,
                    context=context,
                    max_tokens=500
                )
                if perf:
                    perf.checkpoint("llm_response_generated")
            except Exception as e:
                if self.logger:
                    self.logger.warning("llm_generation", f"LLM generation failed: {e}")
                llm_response = context  # Fallback to context
        
        processing_time = (time.time() - start_time) * 1000
        
        return ChatResponse(
            response=llm_response,
            search_results=search_results,
            timestamp=datetime.utcnow().isoformat(),
            processing_time=processing_time,
            session_id=session_id,
            turn_id=turn_id,
            query_type=query_type,
            tools_used=["semantic_search", "llm_generation"],
            confidence_score=0.7 if search_results else 0.1
        ).model_dump()
    
    def _handle_casual_conversation(self, message: str) -> str:
        """Handle casual conversation without database access."""
        message_lower = message.lower().strip()
        
        if any(greeting in message_lower for greeting in ["hi", "hello", "hey"]):
            responses = [
                "Hello! I'm PIO AI, your AML database assistant. I can help you explore database schemas, analyze data, and answer questions about your AML system.",
                "Hi there! I'm here to help you with AML database queries, table information, and data analysis. What would you like to know?",
                "Hello! I can assist you with database schema exploration, data analysis, and AML-related queries. How can I help you today?"
            ]
            import random
            return random.choice(responses)
            
        elif any(pattern in message_lower for pattern in ["how are you", "what's up"]):
            return "I'm doing well, thank you! I'm ready to help you with your AML database questions. What would you like to explore today?"
            
        elif any(pattern in message_lower for pattern in ["what can you do", "help", "what are you"]):
            return """I'm PIO AI, your intelligent AML database assistant! Here's what I can help you with:

Database Exploration: Ask about table schemas, column information, and database structure
Data Analysis: Query data patterns, null values, record counts, and data quality
Smart Conversations: I remember our conversation context for follow-up questions
AML Expertise: Help with compliance data, transaction monitoring, and risk assessment queries

Try asking me things like:
• "What tables contain customer information?"
• "Show me the schema for transaction tables"
• "How many null values are in the customer table?"
• "What AML-related data do we have?"

What would you like to explore?"""
            
        elif any(pattern in message_lower for pattern in ["thanks", "thank you"]):
            return "You're welcome! Feel free to ask me anything about your AML database or data analysis needs."
            
        elif any(pattern in message_lower for pattern in ["bye", "goodbye"]):
            return "Goodbye! Come back anytime you need help with AML database queries or analysis."
            
        else:
            # Generic conversational response
            return "I understand. Is there anything specific about the AML database or data analysis I can help you with?"
    
    def build_context(self, query: str, max_results: int = 5) -> str:
        """Build detailed context from semantic search results."""
        search_results = self.semantic_search(query, max_results=max_results)
        
        if not search_results:
            return "No relevant database information found for this query."
        
        context_parts = ["=== SPECIFIC DATABASE SEARCH RESULTS ===\n"]
        context_parts.append(f"Search performed for: '{query}'\n")
        
        for i, result in enumerate(search_results, 1):
            metadata = result.get('metadata', {})
            table_name = metadata.get('table_name', 'Unknown')
            owner = metadata.get('owner', 'Unknown')
            entity_type = metadata.get('entity_type', 'Unknown')
            similarity = result['similarity']
            
            context_parts.append(f"RESULT {i}:")
            context_parts.append(f"  Table: {owner}.{table_name}")
            context_parts.append(f"  Type: {entity_type}")
            context_parts.append(f"  Relevance Score: {similarity:.1%}")
            context_parts.append(f"  Database Content:")
            
            # Provide much more content (up to 1000 characters instead of 200)
            full_content = result['content']
            if len(full_content) > 1000:
                context_parts.append(f"    {full_content[:1000]}... [Content truncated - {len(full_content)} total characters]")
            else:
                context_parts.append(f"    {full_content}")
            
            context_parts.append("")
        
        context_parts.append("=== END OF DATABASE SEARCH RESULTS ===")
        context_parts.append("IMPORTANT: Answer ONLY based on the specific information shown above.")
        
        return "\n".join(context_parts)
    
    def generate_response(self, query: str, context: str) -> str:
        """Generate LLM response with context."""
        audit = SystemAudit()
        audit.start_phase("LLM_RESPONSE_GENERATION")
        
        providers = get_available_providers()
        
        if not providers:
            audit.end_phase("LLM_RESPONSE_GENERATION", False, "No LLM providers available")
            return self._generate_fallback_response(query, context)
        
        # Build comprehensive prompt for LLM
        prompt = f"""You are PIO AI, an expert AML database analyst. You MUST answer ONLY based on the specific database information provided below. Do NOT use general knowledge or make assumptions about what data might exist.

USER QUESTION: {query}

AVAILABLE DATABASE INFORMATION:
{context}

CRITICAL INSTRUCTIONS:
1. ONLY answer about information explicitly shown in the database context above
2. If the user asks about columns, tables, or data that is NOT in the provided context, say "I don't have information about that in the current database results"
3. Do NOT make up or assume what columns might exist - only mention what is explicitly shown
4. Do NOT provide general AML knowledge unless it directly relates to the specific data shown
5. Focus on the actual table/column names, data types, and content found in the search results
6. If asking about a specific table but the search results don't contain detailed column information, say "The search results show this table exists but I need more specific information to describe its columns"
7. Quote directly from the database content when describing what data is available
8. If no relevant data is found, suggest more specific search terms

RESPOND ONLY BASED ON THE PROVIDED DATABASE CONTEXT - DO NOT USE GENERAL KNOWLEDGE ABOUT AML SYSTEMS.

EXPERT RESPONSE:"""

        try:
            response = None
            
            # Debug: Check LLM manager availability
            audit_logger.info(f"LLM Manager available: {self.llm_manager is not None}")
            if self.llm_manager:
                audit_logger.info(f"Available providers: {get_available_providers()}")
            
            # Try using LLM manager chat method
            if self.llm_manager:
                audit.start_phase("LLM_MANAGER_REQUEST")
                try:
                    messages = [{"role": "user", "content": prompt}]
                    audit_logger.info("📤 Sending request to LLM...")
                    llm_response = self.llm_manager.chat(messages)
                    
                    # Extract content from LLMResponse object
                    if hasattr(llm_response, 'content'):
                        response = llm_response.content
                        audit.end_phase("LLM_MANAGER_REQUEST", True, f"Response length: {len(response)} chars")
                        audit_logger.info(f"LLM Response received: {len(response)} characters")
                    else:
                        response = str(llm_response)
                        audit.end_phase("LLM_MANAGER_REQUEST", True, f"String response: {len(response)} chars")
                        audit_logger.info(f"LLM Response (string): {len(response)} characters")
                        
                except Exception as llm_error:
                    audit.end_phase("LLM_MANAGER_REQUEST", False, str(llm_error))
                    audit_logger.error(f"LLM Manager error: {llm_error}")
                    response = None
            
            # Fallback to direct Cohere if LLM manager fails
            if not response:
                audit.start_phase("COHERE_FALLBACK")
                audit_logger.info("Trying direct Cohere Chat API fallback...")
                try:
                    import cohere
                    import os
                    
                    api_key = os.getenv("COHERE_API_KEY")
                    audit_logger.info(f"🔑 Cohere API key available: {api_key is not None}")
                    if api_key:
                        co = cohere.Client(api_key)
                        chat_response = co.chat(
                            model='command-r-08-2024',  # Use the supported model
                            message=prompt,
                            max_tokens=800,
                            temperature=0.7
                        )
                        response = chat_response.text
                        audit.end_phase("COHERE_FALLBACK", True, f"Response length: {len(response)} chars")
                        audit_logger.info(f"Direct Cohere Chat response: {len(response)} characters")
                    else:
                        audit.end_phase("COHERE_FALLBACK", False, "No API key")
                        response = None
                except Exception as cohere_error:
                    audit.end_phase("COHERE_FALLBACK", False, str(cohere_error))
                    audit_logger.error(f"Cohere error: {cohere_error}")
                    response = None
            
            if response:
                audit.end_phase("LLM_RESPONSE_GENERATION", True, f"Final response: {len(response)} chars")
                return response
            else:
                audit.end_phase("LLM_RESPONSE_GENERATION", False, "All LLM methods failed")
                return self._generate_fallback_response(query, context)
                
        except Exception as e:
            audit.end_phase("LLM_RESPONSE_GENERATION", False, str(e))
            audit_logger.error(f"Error generating LLM response: {e}")
            return self._generate_fallback_response(query, context)
    
    def _generate_fallback_response(self, query: str, context: str) -> str:
        """Generate an intelligent fallback response when LLM is not available."""
        search_results = self.semantic_search(query, max_results=3)
        
        if not search_results:
            return f"I couldn't find specific information about '{query}' in the AML database. This could mean:\n" \
                   f"• The information doesn't exist in the current database\n" \
                   f"• Try using different keywords or terms\n" \
                   f"• Consider asking about specific table names, data types, or AML processes\n\n" \
                   f"**Suggestions:** Try asking about 'customer data', 'transaction monitoring', 'risk assessment', or 'compliance tables'."
        
        # Analyze query to provide better context
        query_lower = query.lower()
        context_hints = []
        
        if any(term in query_lower for term in ['customer', 'client', 'party']):
            context_hints.append("🏢 **Customer/Party Data**: These tables likely contain customer identification, KYC information, and party relationships.")
        
        if any(term in query_lower for term in ['transaction', 'payment', 'transfer']):
            context_hints.append("💳 **Transaction Data**: These tables track financial movements, payment patterns, and transaction monitoring.")
        
        if any(term in query_lower for term in ['risk', 'score', 'rating']):
            context_hints.append("⚠️ **Risk Assessment**: These tables contain risk scores, ratings, and compliance assessments.")
        
        if any(term in query_lower for term in ['alert', 'suspicious', 'aml']):
            context_hints.append("🚨 **AML Monitoring**: These tables manage alerts, suspicious activity reports, and compliance workflows.")
        
        response_parts = [f"**PIO AI Analysis for: '{query}'**\n"]
        
        if context_hints:
            response_parts.extend(context_hints)
            response_parts.append("")
        
        response_parts.append("**Relevant Database Elements:**\n")
        
        for i, result in enumerate(search_results, 1):
            metadata = result.get('metadata', {})
            table_name = metadata.get('table_name', 'Unknown')
            owner = metadata.get('owner', 'Unknown')
            similarity = result['similarity']
            
            # Provide confidence level based on similarity
            confidence = "High" if similarity > 0.8 else "Medium" if similarity > 0.5 else "Low"
            
            response_parts.append(f"**{i}. {owner}.{table_name}** (Relevance: {confidence} - {similarity:.1%})")
            
            # Extract meaningful content description
            content = result['content'][:200]
            if 'COLUMN_NAME' in content.upper():
                response_parts.append(f"   Purpose: Database schema information containing column definitions and structure")
            elif any(term in content.upper() for term in ['CUSTOMER', 'PARTY', 'CLIENT']):
                response_parts.append(f"   Purpose: Customer/party management and identification data")
            elif any(term in content.upper() for term in ['TRANSACTION', 'PAYMENT']):
                response_parts.append(f"   Purpose: Transaction processing and financial data tracking")
            elif any(term in content.upper() for term in ['RISK', 'SCORE']):
                response_parts.append(f"   Purpose: Risk assessment and scoring mechanisms")
            else:
                response_parts.append(f"   Content: {content}...")
            
            response_parts.append("")
        
        response_parts.append("Next Steps: Ask specific questions like:")
        response_parts.append("• 'What columns are in the [table_name] table?'")
        response_parts.append("• 'How is risk scoring calculated?'")
        response_parts.append("• 'What customer data is stored?'")
        response_parts.append("• 'Show me transaction monitoring tables'")
        
        return "\n".join(response_parts)

# API Routes
@app.get("/", response_class=HTMLResponse)
async def get_chat_interface():
    """Serve the main chat interface."""
    html_content = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>PIO AI - AML Database Intelligence</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body { 
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; 
            background: linear-gradient(135deg, #1e3c72 0%, #2a5298 50%, #4a90e2 100%);
            height: 100vh; 
            display: flex; 
            align-items: center; 
            justify-content: center;
        }
        .chat-container { 
            background: white; 
            border-radius: 16px; 
            box-shadow: 0 25px 50px rgba(0,0,0,0.15); 
            width: 90%; 
            max-width: 900px; 
            height: 90vh; 
            display: flex; 
            flex-direction: column;
            overflow: hidden;
            border: 1px solid rgba(255,255,255,0.1);
        }
        .chat-header { 
            background: linear-gradient(135deg, #1e3c72, #2a5298); 
            color: white; 
            padding: 24px; 
            text-align: center;
            border-radius: 16px 16px 0 0;
            position: relative;
            overflow: hidden;
        }
        .chat-header::before {
            content: '';
            position: absolute;
            top: 0;
            left: 0;
            right: 0;
            bottom: 0;
            background: url('data:image/svg+xml,<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100"><defs><pattern id="grid" width="10" height="10" patternUnits="userSpaceOnUse"><path d="M 10 0 L 0 0 0 10" fill="none" stroke="rgba(255,255,255,0.05)" stroke-width="1"/></pattern></defs><rect width="100" height="100" fill="url(%23grid)"/></svg>');
            opacity: 0.3;
        }
        .chat-header h1 { 
            font-size: 28px; 
            margin-bottom: 8px; 
            font-weight: 600;
            position: relative;
            z-index: 1;
        }
        .chat-header .logo {
            font-size: 32px;
            font-weight: 700;
            background: linear-gradient(45deg, #ffffff, #a8d8ff);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            background-clip: text;
            margin-bottom: 4px;
        }
        .chat-header p { 
            opacity: 0.9; 
            font-size: 15px; 
            position: relative;
            z-index: 1;
            font-weight: 300;
        }
        .chat-messages { 
            flex: 1; 
            padding: 24px; 
            overflow-y: auto; 
            background: #f8fafc;
        }
        .message { 
            margin-bottom: 20px; 
            display: flex; 
            align-items: flex-start;
        }
        .message.user { flex-direction: row-reverse; }
        .message-content { 
            max-width: 75%; 
            padding: 16px 20px; 
            border-radius: 18px; 
            position: relative;
            word-wrap: break-word;
            font-size: 14px;
            line-height: 1.5;
        }
        .message.user .message-content { 
            background: linear-gradient(135deg, #1e3c72, #2a5298); 
            color: white; 
            margin-left: 20px;
            box-shadow: 0 4px 12px rgba(30, 60, 114, 0.3);
        }
        .message.assistant .message-content { 
            background: white; 
            border: 1px solid #e2e8f0; 
            margin-right: 20px;
            box-shadow: 0 2px 8px rgba(0,0,0,0.05);
            color: #2d3748;
        } 
            margin-right: 20px;
            box-shadow: 0 2px 10px rgba(0,0,0,0.05);
        }
        .message-avatar { 
            width: 44px; 
            height: 44px; 
            border-radius: 50%; 
            display: flex; 
            align-items: center; 
            justify-content: center; 
            font-weight: 600;
            font-size: 14px;
            box-shadow: 0 2px 8px rgba(0,0,0,0.1);
        }
        .message.user .message-avatar { 
            background: linear-gradient(135deg, #1e3c72, #2a5298); 
            color: white; 
        }
        .message.assistant .message-avatar { 
            background: linear-gradient(135deg, #4a90e2, #357abd); 
            color: white; 
        }
        .chat-input { 
            padding: 24px; 
            border-top: 1px solid #e2e8f0; 
            display: flex; 
            gap: 12px;
            background: white;
            border-radius: 0 0 16px 16px;
        }
        .chat-input input { 
            flex: 1; 
            padding: 16px 20px; 
            border: 2px solid #e2e8f0; 
            border-radius: 25px; 
            font-size: 15px;
            outline: none;
            transition: all 0.3s ease;
            font-family: inherit;
        }
        .chat-input input:focus { 
            border-color: #2a5298; 
            box-shadow: 0 0 0 3px rgba(42, 82, 152, 0.1);
        }
        .chat-input button { 
            padding: 16px 28px; 
            background: linear-gradient(135deg, #1e3c72, #2a5298); 
            color: white; 
            border: none; 
            border-radius: 25px; 
            cursor: pointer; 
            font-size: 15px;
            font-weight: 600;
            transition: all 0.3s ease;
            box-shadow: 0 4px 12px rgba(30, 60, 114, 0.3);
        }
        .chat-input button:hover { 
            transform: translateY(-2px); 
            box-shadow: 0 6px 16px rgba(30, 60, 114, 0.4);
        }
        .chat-input button:disabled { 
            opacity: 0.6; 
            cursor: not-allowed; 
            transform: none;
            box-shadow: 0 4px 12px rgba(30, 60, 114, 0.2);
        }
        .loading { 
            display: flex; 
            align-items: center; 
            gap: 12px; 
            color: #4a5568;
            font-weight: 500;
        }
        .loading-dots { 
            display: flex; 
            gap: 4px;
        }
        .loading-dots div { 
            width: 8px; 
            height: 8px; 
            background: #2a5298; 
            border-radius: 50%; 
            animation: bounce 1.4s ease-in-out infinite both;
        }
        .loading-dots div:nth-child(1) { animation-delay: -0.32s; }
        .loading-dots div:nth-child(2) { animation-delay: -0.16s; }
        @keyframes bounce {
            0%, 80%, 100% { transform: scale(0); }
            40% { transform: scale(1); }
        }
        .search-results { 
            margin-top: 12px; 
            padding: 12px 16px; 
            background: linear-gradient(135deg, #f0f9ff, #e0f2fe); 
            border-radius: 12px; 
            font-size: 13px;
            border-left: 4px solid #2a5298;
            color: #1e3a8a;
        }
        .examples { 
            padding: 28px; 
            text-align: center; 
            color: #4a5568; 
            color: #666;
        }
        .examples h3 { 
            margin-bottom: 18px; 
            color: #1e3c72; 
            font-weight: 600;
            font-size: 18px;
        }
        .examples .example-buttons { 
            display: flex; 
            flex-wrap: wrap; 
            gap: 12px; 
            justify-content: center;
        }
        .examples button { 
            padding: 12px 20px; 
            background: linear-gradient(135deg, #f7fafc, #edf2f7); 
            border: 2px solid #e2e8f0; 
            border-radius: 25px; 
            cursor: pointer; 
            font-size: 13px;
            font-weight: 500;
            transition: all 0.3s ease;
            color: #2d3748;
        }
        .examples button:hover { 
            background: linear-gradient(135deg, #1e3c72, #2a5298); 
            color: white; 
            border-color: #1e3c72;
            transform: translateY(-2px);
            box-shadow: 0 4px 12px rgba(30, 60, 114, 0.2);
        }
    </style>
</head>
<body>
    <div class="chat-container">
        <div class="chat-header">
            <div class="logo">PIO AI</div>
            <h1>AML Database Intelligence</h1>
            <p>Advanced semantic search powered by BGE-large-en-v1.5 for comprehensive AML analysis</p>
        </div>
        
        <div class="chat-messages" id="chatMessages">
            <div class="examples">
                <h3>Try asking about:</h3>
                <div class="example-buttons">
                    <button onclick="askExample('What customer information is available?')">Customer Info</button>
                    <button onclick="askExample('Show me transaction tables')">Transactions</button>
                    <button onclick="askExample('What risk assessment data exists?')">Risk Assessment</button>
                    <button onclick="askExample('Are there suspicious activity tables?')">Suspicious Activity</button>
                    <button onclick="askExample('What payment data is stored?')">Payment Data</button>
                    <button onclick="askExample('Show me AML compliance tables')">AML Compliance</button>
                </div>
            </div>
        </div>
        
        <div class="chat-input">
            <input type="text" id="messageInput" placeholder="Ask PIO AI about your AML database..." 
                   onkeypress="if(event.key==='Enter') sendMessage()">
            <button onclick="sendMessage()" id="sendButton">Send</button>
        </div>
    </div>

    <script>
        // Session management
        let currentSessionId = null;
        
        function addMessage(content, isUser = false, searchResults = null) {
            const messagesDiv = document.getElementById('chatMessages');
            const messageDiv = document.createElement('div');
            messageDiv.className = `message ${isUser ? 'user' : 'assistant'}`;
            
            const avatar = document.createElement('div');
            avatar.className = 'message-avatar';
            avatar.textContent = isUser ? 'You' : 'PIO';
            
            const messageContent = document.createElement('div');
            messageContent.className = 'message-content';
            messageContent.innerHTML = content.replace(/\\n/g, '<br>');
            
            if (!isUser && searchResults && searchResults.length > 0) {
                const resultsDiv = document.createElement('div');
                resultsDiv.className = 'search-results';
                resultsDiv.innerHTML = `
                    <strong>Found ${searchResults.length} relevant items:</strong><br>
                    ${searchResults.slice(0, 3).map(r => 
                        `• ${r.metadata.owner}.${r.metadata.table_name} (${(r.similarity * 100).toFixed(1)}% match)`
                    ).join('<br>')}
                `;
                messageContent.appendChild(resultsDiv);
            }
            
            messageDiv.appendChild(avatar);
            messageDiv.appendChild(messageContent);
            messagesDiv.appendChild(messageDiv);
            messagesDiv.scrollTop = messagesDiv.scrollHeight;
        }
        
        function addLoadingMessage() {
            const messagesDiv = document.getElementById('chatMessages');
            const messageDiv = document.createElement('div');
            messageDiv.className = 'message assistant';
            messageDiv.id = 'loadingMessage';
            
            const avatar = document.createElement('div');
            avatar.className = 'message-avatar';
            avatar.textContent = 'PIO';
            
            const messageContent = document.createElement('div');
            messageContent.className = 'message-content loading';
            messageContent.innerHTML = `
                Searching database...
                <div class="loading-dots">
                    <div></div><div></div><div></div>
                </div>
            `;
            
            messageDiv.appendChild(avatar);
            messageDiv.appendChild(messageContent);
            messagesDiv.appendChild(messageDiv);
            messagesDiv.scrollTop = messagesDiv.scrollHeight;
        }
        
        function removeLoadingMessage() {
            const loadingMessage = document.getElementById('loadingMessage');
            if (loadingMessage) {
                loadingMessage.remove();
            }
        }
        
        async function sendMessage() {
            const input = document.getElementById('messageInput');
            const button = document.getElementById('sendButton');
            const message = input.value.trim();
            
            if (!message) return;
            
            // Add user message
            addMessage(message, true);
            input.value = '';
            button.disabled = true;
            
            // Add loading message
            addLoadingMessage();
            
            try {
                const requestBody = { message: message };
                if (currentSessionId) {
                    requestBody.session_id = currentSessionId;
                }
                
                const response = await fetch('/chat', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                    },
                    body: JSON.stringify(requestBody)
                });
                
                const data = await response.json();
                
                // Store session ID for future requests
                if (data.session_id) {
                    currentSessionId = data.session_id;
                }
                
                removeLoadingMessage();
                
                if (response.ok) {
                    addMessage(data.response, false, data.search_results);
                } else {
                    addMessage(`Error: ${data.detail || 'Something went wrong'}`, false);
                }
            } catch (error) {
                removeLoadingMessage();
                addMessage(`Error: ${error.message}`, false);
            }
            
            button.disabled = false;
            input.focus();
        }
        
        function askExample(question) {
            document.getElementById('messageInput').value = question;
            sendMessage();
        }
        
        // Clear examples on first message
        let firstMessage = true;
        const originalAddMessage = addMessage;
        addMessage = function(...args) {
            if (firstMessage && args[1]) { // If it's a user message
                document.querySelector('.examples').style.display = 'none';
                firstMessage = false;
            }
            originalAddMessage.apply(this, args);
        };
        
        // Focus input on load
        document.getElementById('messageInput').focus();
    </script>
</body>
</html>
    """
    return HTMLResponse(content=html_content)

@app.post("/chat", response_model=ChatResponse)
async def chat_endpoint(message: ChatMessage, background_tasks: BackgroundTasks):
    """Enhanced chat endpoint with agentic behavior and observability."""
    if not chatbot:
        raise HTTPException(status_code=500, detail="Chat bot not initialized")
    
    try:
        # Use the enhanced chat processing
        response = await chatbot.process_chat_message(
            message=message.message,
            session_id=message.session_id,
            user_id=message.user_id
        )
        
        # Log metrics in background
        if chatbot.observability and chatbot.observability.get_metrics_collector():
            background_tasks.add_task(
                chatbot.observability.get_metrics_collector().record_query_metrics,
                query_type=response.get("query_type", "unknown"),
                duration_ms=response.get("processing_time", 0),
                success=True,
                confidence_score=response.get("confidence_score", 0.0),
                tools_used=response.get("tools_used", []),
                session_id=response.get("session_id")
            )
        
        return response
        
    except Exception as e:
        # Log error metrics
        if chatbot.observability and chatbot.observability.get_metrics_collector():
            background_tasks.add_task(
                chatbot.observability.get_metrics_collector().record_query_metrics,
                query_type="error",
                duration_ms=0,
                success=False,
                confidence_score=0.0,
                tools_used=[],
                session_id=message.session_id
            )
        
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/system/status")
async def system_status():
    """Get comprehensive system status."""
    if not chatbot:
        return SystemStatus(
            status="uninitialized",
            timestamp=datetime.utcnow().isoformat(),
            components={"chatbot": "not_initialized"},
            performance_stats={},
            agent_available=False,
            storage_layer="unknown"
        )
    
    try:
        components = {
            "bge_model": "ready" if chatbot.bge_model else "not_loaded",
            "chroma_client": "ready" if chatbot.chroma_client else "not_connected",
            "collections": f"{len(chatbot.collections)}_loaded" if chatbot.collections else "none",
            "llm_manager": "ready" if chatbot.llm_manager else "not_available"
        }
        
        # Production components status
        if hasattr(chatbot, 'observability') and chatbot.observability:
            components["observability"] = "enabled"
        if hasattr(chatbot, 'performance_optimizer') and chatbot.performance_optimizer:
            components["performance_optimizer"] = "enabled"
        if hasattr(chatbot, 'agent_orchestrator') and chatbot.agent_orchestrator:
            components["agent_orchestrator"] = "enabled"
        if hasattr(chatbot, 'parquet_layer') and chatbot.parquet_layer:
            components["parquet_storage"] = "ready"
        
        # Get performance stats
        performance_stats = {}
        if hasattr(chatbot, 'performance_optimizer') and chatbot.performance_optimizer:
            performance_stats = chatbot.performance_optimizer.get_performance_stats()
        
        # Get observability health check
        if hasattr(chatbot, 'observability') and chatbot.observability:
            observability_health = chatbot.observability.health_check()
            components.update(observability_health.get("components", {}))
            performance_stats.update(observability_health.get("statistics", {}))
        
        overall_status = "healthy"
        if any("error" in status or "not_" in status for status in components.values()):
            overall_status = "degraded"
        
        return SystemStatus(
            status=overall_status,
            timestamp=datetime.utcnow().isoformat(),
            components=components,
            performance_stats=performance_stats,
            agent_available=bool(hasattr(chatbot, 'agent_orchestrator') and chatbot.agent_orchestrator),
            storage_layer="parquet" if hasattr(chatbot, 'parquet_layer') and chatbot.parquet_layer else "legacy"
        )
        
    except Exception as e:
        return SystemStatus(
            status="error",
            timestamp=datetime.utcnow().isoformat(),
            components={"error": str(e)},
            performance_stats={},
            agent_available=False,
            storage_layer="unknown"
        )

@app.get("/search")
async def search_endpoint(query: str, max_results: int = 5):
    """Direct search endpoint."""
    if not chatbot:
        raise HTTPException(status_code=500, detail="Chat bot not initialized")
    
    try:
        results = chatbot.semantic_search(query, max_results=max_results)
        return JSONResponse(content={"query": query, "results": results})
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/status")
async def status_endpoint():
    """Get system status."""
    if not chatbot:
        return {"status": "not_initialized"}
    
    providers = get_available_providers()
    collections_info = {name: coll.count() for name, coll in chatbot.collections.items()}
    
    return {
        "status": "ready",
        "bge_model": "BAAI/bge-large-en-v1.5" if chatbot.bge_model else None,
        "collections": collections_info,
        "llm_providers": providers
    }

if __name__ == "__main__":
    import uvicorn
    print("Starting AML Chat Web Interface...")
    print("Open your browser and go to: http://localhost:8010")
    print("Or try: http://127.0.0.1:8010")
    uvicorn.run(app, host="127.0.0.1", port=8010)