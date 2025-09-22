
"""
Web Chat Interface for AML Database with BGE Semantic Search
"""

import sys
import os
from pathlib import Path
import json
from typing import List, Dict, Any
from datetime import datetime

# Add package to path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

try:
    from fastapi import FastAPI, HTTPException, Request
    from fastapi.staticfiles import StaticFiles
    from fastapi.responses import HTMLResponse, JSONResponse
    from pydantic import BaseModel
    import chromadb
    from chromadb.config import Settings
    from sentence_transformers import SentenceTransformer
    from services.llm.provider import get_available_providers, llm_manager
    from services.db.catalog_store import CatalogStore
    print("✅ Required packages imported successfully")
except ImportError as e:
    print(f"❌ Import error: {e}")
    sys.exit(1)

# Pydantic models
class ChatMessage(BaseModel):
    message: str
    max_results: int = 5

class ChatResponse(BaseModel):
    response: str
    search_results: List[Dict[str, Any]]
    timestamp: str
    processing_time: float

# Initialize FastAPI app
app = FastAPI(
    title="AML Database Chat API",
    description="Chat interface for AML database with BGE semantic search",
    version="1.0.0"
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
            
            status = "✅" if success else "❌"
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
    """Web-based chat interface for AML database."""
    
    def __init__(self):
        self.bge_model = None
        self.chroma_client = None
        self.catalog_store = None
        self.collections = {}
        self.embedding_dimension = None
        
        # Initialize LLM manager safely
        try:
            from services.llm.provider import LLMManager
            self.llm_manager = LLMManager()
            print("✅ LLM Manager initialized")
        except Exception as e:
            print(f"⚠️ LLM Manager initialization failed: {e}")
            self.llm_manager = None
        
    def initialize(self):
        """Initialize all components."""
        audit = SystemAudit()
        print("🤖 Initializing AML Web Chat Bot...")
        
        # Initialize BGE model
        audit.start_phase("BGE_MODEL_LOADING")
        try:
            print("🧠 Loading BGE-large-en-v1.5 model...")
            self.bge_model = SentenceTransformer('BAAI/bge-large-en-v1.5')
            self.embedding_dimension = self.bge_model.get_sentence_embedding_dimension()
            audit.end_phase("BGE_MODEL_LOADING", True, f"Dimension: {self.embedding_dimension}")
            print(f"✅ BGE model loaded (dimension: {self.embedding_dimension})")
        except Exception as e:
            audit.end_phase("BGE_MODEL_LOADING", False, str(e))
            raise
        
        # Initialize ChromaDB
        audit.start_phase("CHROMADB_INIT")
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
            audit.end_phase("CHROMADB_INIT", True, f"Path: {chroma_path}")
        except Exception as e:
            audit.end_phase("CHROMADB_INIT", False, str(e))
            raise
        
        # Load collections with dimension validation
        audit.start_phase("COLLECTION_LOADING")
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
                    print(f"📊 Loaded collection '{collection.name}' with {count} embeddings ({dimension_info})")
                
            except Exception as e:
                audit_logger.error(f"❌ Error loading collection {collection.name}: {e}")
                
        if dimension_issues:
            audit.end_phase("COLLECTION_LOADING", False, f"Dimension mismatches: {'; '.join(dimension_issues)}")
        else:
            audit.end_phase("COLLECTION_LOADING", True, f"Loaded {len(self.collections)} collections: {', '.join(collection_details)}")
        
        # Prioritize the comprehensive dictionary metadata collection
        if 'aml_dictionary_metadata' in self.collections:
            print("🎯 Using comprehensive dictionary metadata as primary source")
            # Move it to the front for priority searching
            primary_collection = self.collections.pop('aml_dictionary_metadata')
            self.collections = {'aml_dictionary_metadata': primary_collection, **self.collections}
        
        # Initialize catalog store
        catalog_db_path = warehouse_path / "catalog.db"
        self.catalog_store = CatalogStore(str(catalog_db_path))
        
        print("✅ AML Web Chat Bot initialized successfully!")
        
    def semantic_search(self, query: str, max_results: int = 5) -> List[Dict[str, Any]]:
        """Perform semantic search across all collections."""
        audit = SystemAudit()
        audit.start_phase("SEMANTIC_SEARCH")
        
        all_results = []
        search_details = []
        
        if not self.bge_model or not self.collections:
            audit.end_phase("SEMANTIC_SEARCH", False, "Missing model or collections")
            return []
        
        # Generate BGE embedding for query
        audit.start_phase("QUERY_EMBEDDING")
        try:
            query_embedding = self.bge_model.encode([query])[0].tolist()
            audit.end_phase("QUERY_EMBEDDING", True, f"Generated {len(query_embedding)}D embedding")
        except Exception as e:
            audit.end_phase("QUERY_EMBEDDING", False, str(e))
            return []
        
        # Search in all collections
        for collection_name, collection in self.collections.items():
            collection_audit = SystemAudit()
            collection_audit.start_phase(f"SEARCH_{collection_name}")
            
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
                
                collection_audit.end_phase(f"SEARCH_{collection_name}", True, f"Found {result_count} results")
                search_details.append(f"{collection_name}:{result_count}")
                
            except Exception as e:
                collection_audit.end_phase(f"SEARCH_{collection_name}", False, str(e))
                audit_logger.error(f"❌ Error searching {collection_name}: {e}")
                search_details.append(f"{collection_name}:ERROR")
        
        # Sort by similarity and return top results
        final_results = sorted(all_results, key=lambda x: x['similarity'], reverse=True)[:max_results]
        audit.end_phase("SEMANTIC_SEARCH", True, f"Collections searched: {', '.join(search_details)}, Final results: {len(final_results)}")
        
        return final_results
    
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
            audit_logger.info(f"🤖 LLM Manager available: {self.llm_manager is not None}")
            if self.llm_manager:
                audit_logger.info(f"🔧 Available providers: {get_available_providers()}")
            
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
                        audit_logger.info(f"📥 LLM Response received: {len(response)} characters")
                    else:
                        response = str(llm_response)
                        audit.end_phase("LLM_MANAGER_REQUEST", True, f"String response: {len(response)} chars")
                        audit_logger.info(f"📥 LLM Response (string): {len(response)} characters")
                        
                except Exception as llm_error:
                    audit.end_phase("LLM_MANAGER_REQUEST", False, str(llm_error))
                    audit_logger.error(f"❌ LLM Manager error: {llm_error}")
                    response = None
            
            # Fallback to direct Cohere if LLM manager fails
            if not response:
                audit.start_phase("COHERE_FALLBACK")
                audit_logger.info("🔄 Trying direct Cohere Chat API fallback...")
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
                        audit_logger.info(f"✅ Direct Cohere Chat response: {len(response)} characters")
                    else:
                        audit.end_phase("COHERE_FALLBACK", False, "No API key")
                        response = None
                except Exception as cohere_error:
                    audit.end_phase("COHERE_FALLBACK", False, str(cohere_error))
                    audit_logger.error(f"❌ Cohere error: {cohere_error}")
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
                response_parts.append(f"   📊 **Purpose**: Database schema information containing column definitions and structure")
            elif any(term in content.upper() for term in ['CUSTOMER', 'PARTY', 'CLIENT']):
                response_parts.append(f"   👤 **Purpose**: Customer/party management and identification data")
            elif any(term in content.upper() for term in ['TRANSACTION', 'PAYMENT']):
                response_parts.append(f"   💰 **Purpose**: Transaction processing and financial data tracking")
            elif any(term in content.upper() for term in ['RISK', 'SCORE']):
                response_parts.append(f"   📈 **Purpose**: Risk assessment and scoring mechanisms")
            else:
                response_parts.append(f"   📋 **Content**: {content}...")
            
            response_parts.append("")
        
        response_parts.append("💡 **Next Steps**: Ask specific questions like:")
        response_parts.append("• 'What columns are in the [table_name] table?'")
        response_parts.append("• 'How is risk scoring calculated?'")
        response_parts.append("• 'What customer data is stored?'")
        response_parts.append("• 'Show me transaction monitoring tables'")
        
        return "\n".join(response_parts)

# Initialize chatbot on startup
@app.on_event("startup")
async def startup_event():
    global chatbot
    chatbot = AMLWebChatBot()
    chatbot.initialize()

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
                <h3>💡 Try asking about:</h3>
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
                    <strong>🔍 Found ${searchResults.length} relevant items:</strong><br>
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
                const response = await fetch('/chat', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                    },
                    body: JSON.stringify({ message: message })
                });
                
                const data = await response.json();
                
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
async def chat_endpoint(message: ChatMessage):
    """Process chat message and return response."""
    if not chatbot:
        raise HTTPException(status_code=500, detail="Chat bot not initialized")
    
    try:
        import time
        start_time = time.time()
        
        # Get search results
        search_results = chatbot.semantic_search(message.message, max_results=message.max_results)
        
        # Build context
        context = chatbot.build_context(message.message, max_results=message.max_results)
        
        # Generate response
        response = chatbot.generate_response(message.message, context)
        
        processing_time = time.time() - start_time
        
        return ChatResponse(
            response=response,
            search_results=search_results,
            timestamp=datetime.now().isoformat(),
            processing_time=processing_time
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

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
    print("🌐 Starting AML Chat Web Interface...")
    print("📍 Open your browser and go to: http://localhost:8009")
    print("🔗 Or try: http://127.0.0.1:8009")
    uvicorn.run(app, host="127.0.0.1", port=8009)