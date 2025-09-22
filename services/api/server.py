"""
Production FastAPI server for AML Database with BGE embeddings and Neo4j graph.
"""

import os
import sys
import traceback
import asyncio
import time
from pathlib import Path
from typing import Dict, Any, Optional, List, Union
from contextlib import asynccontextmanager
from datetime import datetime

# Add package to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

try:
    from fastapi import FastAPI, HTTPException, Depends, BackgroundTasks, Query
    from fastapi.middleware.cors import CORSMiddleware
    from fastapi.responses import JSONResponse
    from pydantic import BaseModel, Field
    import uvicorn
except ImportError:
    raise ImportError("FastAPI not installed. Run: pip install fastapi uvicorn")

# Core services
from services.llm.answer import answer_query, answer_simple, answer_with_context
from services.retriever.hybrid import retrieve, HybridRetriever
from services.tools_api.fs_tools import read_file, list_dir_safe
from services.tools_api.ast_tools import where_is_line, get_symbols_in_file
from services.tools_api.schema_tools import search_schema, describe_table_safe
from services.ingest.manifest_reader import read_manifest, get_project_by_name

# Production AML components
from services.db.catalog_store import CatalogStore
from services.db.graph_store import ProductionGraphStore
import chromadb
from chromadb.config import Settings


# Pydantic models for API
class QueryRequest(BaseModel):
    query: str = Field(..., description="The question or search query")
    project: str = Field(..., description="Project name to search in")
    path: str = Field("", description="Optional file path context")
    line: int = Field(0, description="Optional line number context")
    max_results: int = Field(20, description="Maximum search results")
    include_debug: bool = Field(False, description="Include debug information")


class QueryResponse(BaseModel):
    answer: str
    query_type: str
    project: str
    context_summary: str
    citations: List[str]
    tokens_used: Optional[int] = None
    retrieval_time: Optional[float] = None
    llm_time: Optional[float] = None
    provider_used: Optional[str] = None
    truncated: bool = False
    debug_info: Optional[Dict[str, Any]] = None


class SearchRequest(BaseModel):
    query: str = Field(..., description="Search query")
    search_type: str = Field("hybrid", description="Search type: 'semantic', 'keyword', 'hybrid', 'graph'")
    max_results: int = Field(20, description="Maximum results to return")
    similarity_threshold: float = Field(0.0, description="Minimum similarity score")


class HybridSearchResponse(BaseModel):
    results: List[Dict[str, Any]]
    total: int
    search_type: str
    execution_time: float
    metadata: Dict[str, Any]


class EntitySearchRequest(BaseModel):
    entity_name: str = Field(..., description="Name of the entity to search for")
    entity_type: str = Field("", description="Type of entity (TABLE, COLUMN, etc.)")
    include_relationships: bool = Field(True, description="Include related entities")


class GraphAnalyticsRequest(BaseModel):
    analysis_type: str = Field(..., description="Type of analysis: 'centrality', 'clusters', 'paths', 'patterns'")
    entity_filter: Optional[str] = Field(None, description="Filter entities by name pattern")
    limit: int = Field(100, description="Maximum results")


class AMLInvestigationRequest(BaseModel):
    entity_names: List[str] = Field(..., description="Entities to investigate")
    investigation_type: str = Field("suspicious_patterns", description="Type of investigation")
    depth: int = Field(2, description="Investigation depth")


class FileRequest(BaseModel):
    project: str
    path: str


class LineRequest(BaseModel):
    project: str
    path: str
    line: int


class SchemaSearchRequest(BaseModel):
    query: str
    table_name: str = ""


# Global state for production components
production_state = {
    "catalog_store": None,
    "graph_store": None,
    "chroma_client": None,
    "hybrid_retriever": None,
    "initialized": False
}


class ProductionComponents:
    """Container for production AML components."""
    
    def __init__(self):
        self.catalog_store = None
        self.graph_store = None
        self.chroma_client = None
        self.hybrid_retriever = None
    
    def search_semantic(self, query: str, max_results: int = 20, similarity_threshold: float = 0.0):
        """Search using ChromaDB semantic search."""
        if not self.chroma_client:
            return []
        
        all_results = []
        collections = self.chroma_client.list_collections()
        
        for collection in collections:
            try:
                coll = self.chroma_client.get_collection(collection.name)
                search_results = coll.query(
                    query_texts=[query],
                    n_results=min(max_results, 100)
                )
                
                if search_results['documents'] and search_results['documents'][0]:
                    for i, (doc, score, meta) in enumerate(zip(
                        search_results['documents'][0],
                        search_results['distances'][0], 
                        search_results['metadatas'][0] or [{}] * len(search_results['documents'][0])
                    )):
                        if (1.0 - score) >= similarity_threshold:  # Convert distance to similarity
                            all_results.append({
                                "content": doc,
                                "score": 1.0 - score,
                                "source": f"chromadb_{collection.name}",
                                "metadata": meta,
                                "collection": collection.name
                            })
            except Exception as e:
                print(f"Error searching collection {collection.name}: {e}")
        
        return sorted(all_results, key=lambda x: x["score"], reverse=True)[:max_results]
    
    def search_graph(self, query: str, max_results: int = 20):
        """Search using Neo4j graph database."""
        if not self.graph_store:
            return []
        
        results = []
        try:
            with self.graph_store.driver.session() as session:
                cypher_query = """
                MATCH (n)
                WHERE toLower(n.name) CONTAINS toLower($query)
                   OR toLower(n.description) CONTAINS toLower($query)
                RETURN n.name as name, n.entity_type as type, 
                       n.description as description, labels(n) as labels
                LIMIT $limit
                """
                
                graph_results = session.run(cypher_query, {
                    "query": query,
                    "limit": max_results
                })
                
                for record in graph_results:
                    results.append({
                        "name": record["name"],
                        "entity_type": record["type"], 
                        "description": record["description"],
                        "labels": record["labels"],
                        "source": "neo4j_graph",
                        "score": 1.0
                    })
        except Exception as e:
            print(f"Error searching graph: {e}")
        
        return results
    
    def search_hybrid(self, query: str, max_results: int = 20, similarity_threshold: float = 0.0):
        """Combined search using semantic, graph, and hybrid retriever."""
        results = []
        
        # Semantic search
        semantic_results = self.search_semantic(query, max_results // 2, similarity_threshold)
        results.extend(semantic_results)
        
        # Graph search
        graph_results = self.search_graph(query, max_results // 2)
        results.extend(graph_results)
        
        # Use hybrid retriever if available
        if self.hybrid_retriever:
            try:
                hybrid_results = self.hybrid_retriever.retrieve(
                    query=query,
                    project="oracle",  # Default project
                    max_results=max_results // 3
                )
                
                for hit in hybrid_results:
                    results.append({
                        "content": hit.content,
                        "score": hit.score,
                        "source": f"hybrid_{hit.source}",
                        "metadata": hit.metadata or {},
                        "path": hit.path,
                        "kind": hit.kind
                    })
            except Exception as e:
                print(f"Error in hybrid search: {e}")
        
        # Remove duplicates and sort by score
        unique_results = []
        seen_content = set()
        
        for result in results:
            content_key = result.get("content", "") or result.get("name", "")
            if content_key and content_key not in seen_content:
                seen_content.add(content_key)
                unique_results.append(result)
        
        return sorted(unique_results, key=lambda x: x.get("score", 0), reverse=True)[:max_results]


# Create global instance
production_components = ProductionComponents()


async def initialize_production_components():
    """Initialize production AML database components."""
    global production_state, production_components
    
    if production_state["initialized"]:
        return
    
    try:
        print("🔧 Initializing production AML components...")
        
        # Load configuration
        import yaml
        warehouse_path = Path(__file__).resolve().parents[2] / "warehouse"
        config_path = Path(__file__).resolve().parents[2] / "config" / "database.yaml"
        
        with open(config_path, 'r') as f:
            db_config = yaml.safe_load(f)
        
        # Initialize catalog store
        print("📊 Initializing catalog store...")
        catalog_db_path = warehouse_path / "catalog.db"
        production_components.catalog_store = CatalogStore(str(catalog_db_path))
        production_state["catalog_store"] = production_components.catalog_store
        
        # Initialize ChromaDB client
        print("🔍 Initializing ChromaDB client...")
        chroma_path = warehouse_path / "vectors"
        
        production_components.chroma_client = chromadb.PersistentClient(
            path=str(chroma_path),
            settings=Settings(
                anonymized_telemetry=False,
                allow_reset=True
            )
        )
        production_state["chroma_client"] = production_components.chroma_client
        
        # Initialize graph store
        print("🕸️ Initializing Neo4j graph store...")
        production_components.graph_store = ProductionGraphStore()
        production_state["graph_store"] = production_components.graph_store
        
        # Initialize hybrid retriever
        print("🔄 Initializing hybrid retriever...")
        production_components.hybrid_retriever = HybridRetriever()
        production_state["hybrid_retriever"] = production_components.hybrid_retriever
        
        production_state["initialized"] = True
        print("✅ Production AML components initialized successfully")
        
    except Exception as e:
        print(f"❌ Failed to initialize production components: {e}")
        traceback.print_exc()
        raise


def get_production_components():
    """Get initialized production components."""
    if not production_state["initialized"]:
        raise HTTPException(
            status_code=503, 
            detail="Production components not initialized. Please check server startup."
        )
    
    return production_components


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown logic."""
    # Startup
    print("🚀 PIO-AI Production AML API starting up...")
    
    # Initialize production components
    await initialize_production_components()
    
    # Load manifest and validate projects
    try:
        manifest = read_manifest()
        print(f"📁 Loaded {len(manifest.get('projects', []))} projects from manifest")
    except Exception as e:
        print(f"⚠️ Warning: Could not load manifest: {e}")
    
    # Check LLM providers
    from services.llm.provider import get_available_providers
    providers = get_available_providers()
    print(f"🤖 Available LLM providers: {providers or 'None (using stub mode)'}")
    
    yield
    
    # Shutdown
    print("🛑 PIO-AI Production AML API shutting down...")
    
    # Clean up production components
    if production_components.graph_store:
        production_components.graph_store.close()
    
    production_state["initialized"] = False


# Create FastAPI app
app = FastAPI(
    title="PIO-AI Production AML Database API",
    description="Production Anti-Money Laundering Database API with BGE embeddings and Neo4j graph analytics",
    version="2.0.0",
    lifespan=lifespan
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure as needed for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(Exception)
async def global_exception_handler(request, exc):
    """Global exception handler."""
    return JSONResponse(
        status_code=500,
        content={
            "error": "Internal server error",
            "detail": str(exc),
            "traceback": traceback.format_exc() if os.getenv("DEBUG") else None,
            "timestamp": datetime.now().isoformat()
        }
    )


# Health check endpoints
@app.get("/health")
async def health_check():
    """Comprehensive health check endpoint."""
    from services.llm.provider import get_available_providers
    
    health_status = {
        "status": "healthy",
        "version": "2.0.0",
        "timestamp": datetime.now().isoformat(),
        "components": {}
    }
    
    # Check LLM providers
    health_status["providers"] = get_available_providers()
    
    # Check production components
    try:
        components = get_production_components()
        
        # Test catalog store
        try:
            catalog_tables = components.catalog_store.get_all_tables()[:5]  # Sample test
            health_status["components"]["catalog_store"] = {
                "status": "healthy",
                "sample_tables": len(catalog_tables)
            }
        except Exception as e:
            health_status["components"]["catalog_store"] = {
                "status": "error",
                "error": str(e)
            }
        
        # Test ChromaDB
        try:
            collections = components.chroma_client.list_collections()
            health_status["components"]["chromadb"] = {
                "status": "healthy", 
                "collections": len(collections)
            }
        except Exception as e:
            health_status["components"]["chromadb"] = {
                "status": "error",
                "error": str(e)
            }
        
        # Test Neo4j graph store
        try:
            with components.graph_store.driver.session() as session:
                result = session.run("MATCH (n) RETURN count(n) as node_count LIMIT 1")
                node_count = result.single()["node_count"]
                health_status["components"]["neo4j"] = {
                    "status": "healthy",
                    "node_count": node_count
                }
        except Exception as e:
            health_status["components"]["neo4j"] = {
                "status": "error", 
                "error": str(e)
            }
            
    except HTTPException:
        health_status["components"]["production_stack"] = {
            "status": "not_initialized",
            "error": "Production components not available"
        }
    
    # Determine overall status
    component_statuses = [comp.get("status") for comp in health_status["components"].values()]
    if any(status == "error" for status in component_statuses):
        health_status["status"] = "degraded"
    elif any(status == "not_initialized" for status in component_statuses):
        health_status["status"] = "initializing"
    
    return health_status


@app.get("/health/ready")
async def readiness_check():
    """Readiness probe for production deployment."""
    try:
        get_production_components()
        return {"status": "ready", "timestamp": datetime.now().isoformat()}
    except HTTPException:
        raise HTTPException(status_code=503, detail="Service not ready")


# Production AML Search Endpoints
@app.post("/aml/search", response_model=HybridSearchResponse)
async def aml_search(request: SearchRequest):
    """Production AML database search with multiple search strategies."""
    start_time = time.time()
    
    try:
        components = get_production_components()
        
        results = []
        metadata = {
            "search_strategy": request.search_type,
            "query": request.query,
            "parameters": {
                "max_results": request.max_results,
                "similarity_threshold": request.similarity_threshold
            }
        }
        
        if request.search_type == "semantic":
            results = components.search_semantic(
                request.query, 
                request.max_results, 
                request.similarity_threshold
            )
            metadata["collections_searched"] = len(components.chroma_client.list_collections())
        
        elif request.search_type == "graph":
            results = components.search_graph(request.query, request.max_results)
            metadata["graph_nodes_searched"] = True
        
        elif request.search_type == "hybrid":
            results = components.search_hybrid(
                request.query, 
                request.max_results, 
                request.similarity_threshold
            )
            metadata["hybrid_components"] = ["chromadb", "neo4j", "catalog"]
        
        else:
            raise HTTPException(status_code=400, detail=f"Unsupported search type: {request.search_type}")
        
        execution_time = time.time() - start_time
        
        return HybridSearchResponse(
            results=results,
            total=len(results),
            search_type=request.search_type,
            execution_time=execution_time,
            metadata=metadata
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Search failed: {str(e)}")


@app.post("/aml/entity/search")
async def search_entities(request: EntitySearchRequest):
    """Search for specific entities in the AML database."""
    try:
        catalog_store, graph_store, chroma_client, hybrid_retriever = get_production_components()
        
        results = {
            "entity": None,
            "relationships": [],
            "semantic_matches": [],
            "execution_time": 0
        }
        
        start_time = time.time()
        
        # Search in Neo4j graph
        with graph_store.driver.session() as session:
            # Find exact entity match
            if request.entity_type:
                cypher_query = """
                MATCH (n)
                WHERE n.name = $name AND n.entity_type = $type
                RETURN n
                """
                params = {"name": request.entity_name, "type": request.entity_type}
            else:
                cypher_query = """
                MATCH (n)
                WHERE n.name = $name
                RETURN n
                """
                params = {"name": request.entity_name}
            
            entity_result = session.run(cypher_query, params)
            entity_record = entity_result.single()
            
            if entity_record:
                entity_node = dict(entity_record["n"])
                results["entity"] = entity_node
                
                # Get relationships if requested
                if request.include_relationships:
                    rel_query = """
                    MATCH (n)-[r]-(connected)
                    WHERE n.name = $name
                    RETURN type(r) as relationship_type, 
                           connected.name as connected_name,
                           connected.entity_type as connected_type,
                           startNode(r).name as start_node,
                           endNode(r).name as end_node
                    LIMIT 50
                    """
                    
                    rel_results = session.run(rel_query, {"name": request.entity_name})
                    
                    for rel_record in rel_results:
                        results["relationships"].append({
                            "type": rel_record["relationship_type"],
                            "connected_entity": rel_record["connected_name"],
                            "connected_type": rel_record["connected_type"],
                            "direction": "outgoing" if rel_record["start_node"] == request.entity_name else "incoming"
                        })
        
        # Search for semantic matches in ChromaDB
        collections = chroma_client.list_collections()
        for collection in collections:
            try:
                coll = chroma_client.get_collection(collection.name)
                semantic_results = coll.query(
                    query_texts=[request.entity_name],
                    n_results=5
                )
                
                if semantic_results['documents'] and semantic_results['documents'][0]:
                    for doc, score, meta in zip(
                        semantic_results['documents'][0],
                        semantic_results['distances'][0],
                        semantic_results['metadatas'][0] or [{}] * len(semantic_results['documents'][0])
                    ):
                        results["semantic_matches"].append({
                            "content": doc,
                            "similarity": 1.0 - score,
                            "collection": collection.name,
                            "metadata": meta
                        })
            except Exception as e:
                print(f"Error searching collection {collection.name}: {e}")
        
        results["execution_time"] = time.time() - start_time
        
        return results
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Entity search failed: {str(e)}")


@app.post("/aml/analytics")
async def graph_analytics(request: GraphAnalyticsRequest):
    """Perform graph analytics on the AML database."""
    try:
        catalog_store, graph_store, chroma_client, hybrid_retriever = get_production_components()
        
        results = {
            "analysis_type": request.analysis_type,
            "results": [],
            "execution_time": 0,
            "metadata": {}
        }
        
        start_time = time.time()
        
        with graph_store.driver.session() as session:
            if request.analysis_type == "centrality":
                # Find most connected entities
                cypher_query = """
                MATCH (n)
                WHERE ($filter IS NULL OR n.name CONTAINS $filter)
                WITH n, size((n)-[]->()) + size((n)<-[]-()) as degree
                RETURN n.name as name, n.entity_type as type, degree
                ORDER BY degree DESC
                LIMIT $limit
                """
                
                analytics_results = session.run(cypher_query, {
                    "filter": request.entity_filter,
                    "limit": request.limit
                })
                
                for record in analytics_results:
                    results["results"].append({
                        "entity": record["name"],
                        "entity_type": record["type"],
                        "centrality_score": record["degree"]
                    })
                
                results["metadata"]["metric"] = "degree_centrality"
            
            elif request.analysis_type == "clusters":
                # Find clusters of connected entities
                cypher_query = """
                MATCH (n)-[r]-(m)
                WHERE ($filter IS NULL OR n.name CONTAINS $filter OR m.name CONTAINS $filter)
                WITH n, collect(DISTINCT m.name) as connected_entities
                WHERE size(connected_entities) >= 2
                RETURN n.name as center_entity, n.entity_type as type, connected_entities
                ORDER BY size(connected_entities) DESC
                LIMIT $limit
                """
                
                cluster_results = session.run(cypher_query, {
                    "filter": request.entity_filter,
                    "limit": request.limit
                })
                
                for record in cluster_results:
                    results["results"].append({
                        "center_entity": record["center_entity"],
                        "entity_type": record["type"],
                        "cluster_size": len(record["connected_entities"]),
                        "connected_entities": record["connected_entities"]
                    })
                
                results["metadata"]["clustering_method"] = "direct_connections"
            
            elif request.analysis_type == "paths":
                # Find connection paths between entities
                cypher_query = """
                MATCH path = (start)-[*1..3]-(end)
                WHERE start <> end
                  AND ($filter IS NULL OR start.name CONTAINS $filter OR end.name CONTAINS $filter)
                WITH start.name as start_entity, end.name as end_entity, 
                     length(path) as path_length, count(*) as path_count
                RETURN start_entity, end_entity, path_length, path_count
                ORDER BY path_count DESC, path_length ASC
                LIMIT $limit
                """
                
                path_results = session.run(cypher_query, {
                    "filter": request.entity_filter,
                    "limit": request.limit
                })
                
                for record in path_results:
                    results["results"].append({
                        "start_entity": record["start_entity"],
                        "end_entity": record["end_entity"],
                        "path_length": record["path_length"],
                        "path_count": record["path_count"]
                    })
                
                results["metadata"]["max_path_length"] = 3
            
            elif request.analysis_type == "patterns":
                # Find common relationship patterns
                cypher_query = """
                MATCH (n)-[r]->(m)
                WHERE ($filter IS NULL OR n.name CONTAINS $filter OR m.name CONTAINS $filter)
                WITH type(r) as relationship_type, 
                     n.entity_type as source_type, 
                     m.entity_type as target_type, 
                     count(*) as pattern_count
                RETURN relationship_type, source_type, target_type, pattern_count
                ORDER BY pattern_count DESC
                LIMIT $limit
                """
                
                pattern_results = session.run(cypher_query, {
                    "filter": request.entity_filter,
                    "limit": request.limit
                })
                
                for record in pattern_results:
                    results["results"].append({
                        "relationship_type": record["relationship_type"],
                        "source_type": record["source_type"],
                        "target_type": record["target_type"],
                        "frequency": record["pattern_count"]
                    })
                
                results["metadata"]["analysis_focus"] = "relationship_patterns"
            
            else:
                raise HTTPException(status_code=400, detail=f"Unsupported analysis type: {request.analysis_type}")
        
        results["execution_time"] = time.time() - start_time
        results["metadata"]["total_results"] = len(results["results"])
        
        return results
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Graph analytics failed: {str(e)}")


@app.post("/aml/investigate")
async def aml_investigation(request: AMLInvestigationRequest):
    """Perform AML-specific investigations on entities."""
    try:
        catalog_store, graph_store, chroma_client, hybrid_retriever = get_production_components()
        
        investigation = {
            "investigation_type": request.investigation_type,
            "target_entities": request.entity_names,
            "findings": [],
            "risk_indicators": [],
            "network_analysis": {},
            "execution_time": 0
        }
        
        start_time = time.time()
        
        with graph_store.driver.session() as session:
            if request.investigation_type == "suspicious_patterns":
                # Look for suspicious connection patterns
                for entity in request.entity_names:
                    # Find entities with unusual connectivity
                    pattern_query = """
                    MATCH (target {name: $entity})
                    MATCH (target)-[r*1..$depth]-(connected)
                    WITH target, connected, type(r[0]) as first_relationship, 
                         count(DISTINCT r) as connection_strength
                    WHERE connection_strength > 5  // Threshold for suspicious activity
                    RETURN target.name as target_entity,
                           connected.name as connected_entity,
                           connected.entity_type as connected_type,
                           first_relationship,
                           connection_strength
                    ORDER BY connection_strength DESC
                    LIMIT 10
                    """
                    
                    pattern_results = session.run(pattern_query, {
                        "entity": entity,
                        "depth": request.depth
                    })
                    
                    entity_findings = []
                    for record in pattern_results:
                        entity_findings.append({
                            "connected_entity": record["connected_entity"],
                            "entity_type": record["connected_type"],
                            "relationship_type": record["first_relationship"],
                            "connection_strength": record["connection_strength"],
                            "risk_level": "high" if record["connection_strength"] > 10 else "medium"
                        })
                    
                    if entity_findings:
                        investigation["findings"].append({
                            "target_entity": entity,
                            "pattern_type": "high_connectivity",
                            "findings": entity_findings
                        })
            
            elif request.investigation_type == "network_analysis":
                # Analyze the network around target entities
                entity_list = "', '".join(request.entity_names)
                network_query = f"""
                MATCH (target)
                WHERE target.name IN ['{entity_list}']
                MATCH path = (target)-[r*1..{request.depth}]-(connected)
                WITH target, connected, path, length(path) as distance
                RETURN target.name as target_entity,
                       connected.name as connected_entity,
                       connected.entity_type as connected_type,
                       distance,
                       count(path) as path_count
                ORDER BY target_entity, distance, path_count DESC
                """
                
                network_results = session.run(network_query)
                
                network_map = {}
                for record in network_results:
                    target = record["target_entity"]
                    if target not in network_map:
                        network_map[target] = {"direct": [], "indirect": []}
                    
                    connection_info = {
                        "entity": record["connected_entity"],
                        "type": record["connected_type"],
                        "distance": record["distance"],
                        "path_count": record["path_count"]
                    }
                    
                    if record["distance"] == 1:
                        network_map[target]["direct"].append(connection_info)
                    else:
                        network_map[target]["indirect"].append(connection_info)
                
                investigation["network_analysis"] = network_map
            
            # Generate risk indicators based on findings
            total_high_risk = sum(
                len([f for f in finding["findings"] if f.get("risk_level") == "high"])
                for finding in investigation["findings"]
            )
            
            if total_high_risk > 0:
                investigation["risk_indicators"].append({
                    "indicator": "high_connectivity_entities",
                    "count": total_high_risk,
                    "severity": "high" if total_high_risk > 5 else "medium"
                })
        
        investigation["execution_time"] = time.time() - start_time
        
        return investigation
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"AML investigation failed: {str(e)}")


# Legacy RAG endpoints (maintained for backward compatibility)
@app.post("/query", response_model=QueryResponse)
async def query_endpoint(request: QueryRequest):
    """Main query endpoint for asking questions about code."""
    try:
        response = answer_query(
            query=request.query,
            project=request.project,
            path=request.path,
            line=request.line,
            max_results=request.max_results,
            debug=request.include_debug
        )
        
        return QueryResponse(
            answer=response.answer,
            query_type=response.query_type,
            project=response.project,
            context_summary=response.context_summary,
            citations=response.citations,
            tokens_used=response.tokens_used,
            retrieval_time=response.retrieval_time,
            llm_time=response.llm_time,
            provider_used=response.provider_used,
            truncated=response.truncated,
            debug_info=response.debug_info
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/query/simple")
async def query_simple_endpoint(request: QueryRequest):
    """Simple query endpoint that returns just the answer text."""
    try:
        answer = answer_simple(request.query, request.project)
        return {"answer": answer}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# Legacy search endpoints
@app.post("/search")
async def search_endpoint(request: SearchRequest):
    """Legacy search for code/documents without LLM processing."""
    try:
        # Convert new SearchRequest to old format
        hits = retrieve(
            query=request.query,
            project="oracle",  # Default project
            path="",
            line=0,
            max_results=request.max_results
        )
        
        # Convert hits to JSON-serializable format
        results = []
        for hit in hits:
            results.append({
                "project": hit.project,
                "path": hit.path,
                "kind": hit.kind,
                "source": hit.source,
                "score": hit.score,
                "content": hit.content,
                "start_line": hit.start_line,
                "end_line": hit.end_line,
                "metadata": hit.metadata
            })
        
        return {"results": results, "total": len(results)}
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# File system endpoints
@app.post("/fs/read")
async def read_file_endpoint(request: FileRequest):
    """Read a file from the project."""
    try:
        content = read_file(request.project, request.path)
        if content is None:
            raise HTTPException(status_code=404, detail="File not found or access denied")
        
        return {"content": content, "path": request.path}
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/fs/list")
async def list_dir_endpoint(request: FileRequest):
    """List directory contents."""
    try:
        items = list_dir_safe(request.project, request.path)
        return {"items": items, "path": request.path}
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# AST/Symbol endpoints
@app.post("/ast/line")
async def where_is_line_endpoint(request: LineRequest):
    """Get symbol information for a specific line."""
    try:
        symbol_info = where_is_line(request.project, request.path, request.line)
        if not symbol_info:
            return {"symbol": None, "message": "No symbol found at this line"}
        
        return {"symbol": symbol_info}
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/ast/symbols")
async def get_symbols_endpoint(request: FileRequest):
    """Get all symbols in a file."""
    try:
        symbols = get_symbols_in_file(request.project, request.path)
        return {"symbols": symbols, "path": request.path}
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# Schema endpoints
@app.post("/schema/search")
async def search_schema_endpoint(request: SchemaSearchRequest):
    """Search database schema."""
    try:
        results = search_schema(request.query)
        return {"results": results}
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/schema/table")
async def describe_table_endpoint(request: SchemaSearchRequest):
    """Describe a database table."""
    try:
        if not request.table_name:
            raise HTTPException(status_code=400, detail="table_name is required")
        
        table_info = describe_table_safe(request.table_name)
        if not table_info:
            raise HTTPException(status_code=404, detail="Table not found")
        
        return {"table": table_info}
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# Project management endpoints
@app.get("/projects")
async def list_projects():
    """List all available projects."""
    try:
        manifest = read_manifest()
        projects = manifest.get("projects", [])
        
        # Add project status information
        project_list = []
        for project in projects:
            project_info = {
                "name": project["name"],
                "description": project.get("description", ""),
                "root_path": project["root_path"]
            }
            
            # Check if indexes exist
            package_root = Path(__file__).resolve().parents[2]
            from services.tools_api.ast_tools import sanitize_project_name
            sanitized_name = sanitize_project_name(project["name"])
            
            indexes = {
                "symbols": (package_root / "indexes" / "symbols" / f"{sanitized_name}.sqlite").exists(),
                "graph": (package_root / "indexes" / "graph" / f"{sanitized_name}.sqlite").exists(),
                "bm25": (package_root / "indexes" / "bm25" / sanitized_name).exists(),
                "faiss_code": (package_root / "indexes" / "faiss_code" / f"{sanitized_name}.index").exists(),
                "faiss_text": (package_root / "indexes" / "faiss_text" / f"{sanitized_name}.index").exists()
            }
            
            project_info["indexes"] = indexes
            project_info["indexed"] = any(indexes.values())
            
            project_list.append(project_info)
        
        return {"projects": project_list}
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/projects/{project_name}")
async def get_project_info(project_name: str):
    """Get detailed information about a specific project."""
    try:
        project_info = get_project_by_name(project_name)
        if not project_info:
            raise HTTPException(status_code=404, detail="Project not found")
        
        return {"project": project_info}
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# Configuration endpoints
@app.get("/config/providers")
async def get_providers():
    """Get available LLM providers."""
    from services.llm.provider import get_available_providers, llm_manager
    
    available = get_available_providers()
    all_providers = list(llm_manager.providers.keys())
    
    return {
        "available": available,
        "all": all_providers,
        "default": llm_manager.default_provider
    }


@app.post("/config/provider")
async def set_default_provider(provider_data: dict):
    """Set the default LLM provider."""
    try:
        provider_name = provider_data.get("provider")
        if not provider_name:
            raise HTTPException(status_code=400, detail="provider field required")
        
        from services.llm.provider import set_provider
        set_provider(provider_name)
        
        return {"message": f"Default provider set to {provider_name}"}
        
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# Production deployment information
@app.get("/info")
async def get_api_info():
    """Get comprehensive API information."""
    return {
        "api_name": "PIO-AI Production AML Database API",
        "version": "2.0.0",
        "description": "Production Anti-Money Laundering Database API with BGE embeddings and Neo4j graph analytics",
        "features": {
            "embeddings": "BGE-large-en-v1.5 (1024-dimensional)",
            "vector_database": "ChromaDB with persistent storage",
            "graph_database": "Neo4j with production constraints",
            "search_types": ["semantic", "keyword", "hybrid", "graph"],
            "analytics": ["centrality", "clusters", "paths", "patterns"],
            "investigations": ["suspicious_patterns", "network_analysis"]
        },
        "endpoints": {
            "health": "/health, /health/ready",
            "aml_search": "/aml/search",
            "entity_operations": "/aml/entity/search",
            "analytics": "/aml/analytics", 
            "investigations": "/aml/investigate",
            "legacy_rag": "/query, /search",
            "administration": "/projects, /config"
        },
        "production_features": {
            "async_operations": True,
            "cors_enabled": True,
            "error_handling": "Comprehensive with tracebacks in debug mode",
            "health_monitoring": "Multi-component health checks",
            "scalable_architecture": "Component-based with dependency injection"
        }
    }


if __name__ == "__main__":
    # Configuration
    host = os.getenv("API_HOST", "0.0.0.0")
    port = int(os.getenv("API_PORT", "8080"))
    debug = os.getenv("DEBUG", "false").lower() == "true"
    
    print(f"🚀 Starting PIO-AI Production AML API on {host}:{port}")
    print(f"📚 Documentation available at http://{host}:{port}/docs")
    print(f"🔍 Interactive API at http://{host}:{port}/redoc")
    
    uvicorn.run(
        "server:app",
        host=host,
        port=port,
        reload=debug,
        log_level="info" if not debug else "debug"
    )