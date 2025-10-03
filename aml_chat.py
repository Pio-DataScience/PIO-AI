"""
AML Database Chat Interface with BGE Semantic Search
"""

import sys
import os
from pathlib import Path
import time
import json
from typing import List, Dict, Any, Optional

# Add package to path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

try:
    import chromadb
    from chromadb.config import Settings
    from sentence_transformers import SentenceTransformer
    from services.llm.provider import get_available_providers, llm_manager
    from services.db.catalog_store import CatalogStore
    print("Required packages imported successfully")
except ImportError as e:
    print(f"Import error: {e}")
    sys.exit(1)

class AMLChatBot:
    """Chat interface for AML database with BGE semantic search."""
    
    def __init__(self):
        self.bge_model = None
        self.chroma_client = None
        self.catalog_store = None
        self.collections = {}
        self.conversation_history = []
        
    def initialize(self):
        """Initialize all components."""
        print("Initializing AML Database Chat Bot...")
        
        # Initialize BGE model
        print("Loading BGE-large-en-v1.5 model...")
        self.bge_model = SentenceTransformer('BAAI/bge-large-en-v1.5')
        print(f"BGE model loaded (dimension: {self.bge_model.get_sentence_embedding_dimension()})")
        
        # Initialize ChromaDB
        warehouse_path = Path(__file__).parent / "warehouse"
        chroma_path = warehouse_path / "vectors"
        
        self.chroma_client = chromadb.PersistentClient(
            path=str(chroma_path),
            settings=Settings(
                anonymized_telemetry=False,
                allow_reset=True
            )
        )
        
        # Load collections
        collections = self.chroma_client.list_collections()
        for collection in collections:
            coll = self.chroma_client.get_collection(collection.name)
            if coll.count() > 0:
                self.collections[collection.name] = coll
                print(f"Loaded collection '{collection.name}' with {coll.count()} embeddings")
        
        # Initialize catalog store
        catalog_db_path = warehouse_path / "catalog.db"
        self.catalog_store = CatalogStore(str(catalog_db_path))
        
        # Check LLM providers
        providers = get_available_providers()
        print(f"Available LLM providers: {providers}")
        
        print("AML Chat Bot initialized successfully!")
        
    def semantic_search(self, query: str, max_results: int = 5) -> List[Dict[str, Any]]:
        """Perform semantic search across all collections."""
        all_results = []
        
        if not self.bge_model or not self.collections:
            return all_results
        
        # Generate BGE embedding for query
        query_embedding = self.bge_model.encode([query])[0].tolist()
        
        # Search in all collections
        for collection_name, collection in self.collections.items():
            try:
                search_results = collection.query(
                    query_embeddings=[query_embedding],
                    n_results=max_results
                )
                
                if search_results['documents'] and search_results['documents'][0]:
                    for doc, distance, metadata in zip(
                        search_results['documents'][0],
                        search_results['distances'][0],
                        search_results['metadatas'][0] or [{}] * len(search_results['documents'][0])
                    ):
                        similarity = 1.0 - distance
                        all_results.append({
                            "content": doc,
                            "similarity": similarity,
                            "collection": collection_name,
                            "metadata": metadata or {}
                        })
            except Exception as e:
                print(f"Error searching {collection_name}: {e}")
        
        # Sort by similarity and return top results
        return sorted(all_results, key=lambda x: x['similarity'], reverse=True)[:max_results]
    
    def get_table_details(self, table_name: str) -> Optional[Dict[str, Any]]:
        """Get detailed information about a specific table."""
        try:
            # For now, return basic info since we need to fix catalog_store methods
            return {"table_name": table_name, "note": "Detailed table info coming soon"}
        except Exception as e:
            print(f"Error getting table details: {e}")
        return None
    
    def build_context(self, query: str) -> str:
        """Build context from semantic search results."""
        search_results = self.semantic_search(query, max_results=5)
        
        if not search_results:
            return "No relevant database information found."
        
        context_parts = ["=== RELEVANT DATABASE INFORMATION ===\n"]
        
        for i, result in enumerate(search_results, 1):
            metadata = result.get('metadata', {})
            table_name = metadata.get('table_name', 'Unknown')
            owner = metadata.get('owner', 'Unknown')
            entity_type = metadata.get('entity_type', 'Unknown')
            
            context_parts.append(f"{i}. {entity_type.upper()}: {owner}.{table_name}")
            context_parts.append(f"   Similarity: {result['similarity']:.3f}")
            context_parts.append(f"   Content: {result['content'][:200]}...")
            
            # Get additional table details if it's a table
            if entity_type == 'table' and table_name != 'Unknown':
                table_details = self.get_table_details(table_name)
                if table_details and 'columns' in table_details:
                    columns = table_details['columns']
                    if columns:
                        column_names = [col['column_name'] for col in columns[:5]]  # First 5 columns
                        context_parts.append(f"   Key Columns: {', '.join(column_names)}")
                        if len(columns) > 5:
                            context_parts.append(f"   Total Columns: {len(columns)}")
            
            context_parts.append("")
        
        return "\n".join(context_parts)
    
    def generate_response(self, query: str, context: str) -> str:
        """Generate LLM response with context."""
        providers = get_available_providers()
        
        if not providers:
            return self._generate_fallback_response(query, context)
        
        # Build prompt for LLM
        prompt = f"""You are an expert AML (Anti-Money Laundering) database analyst. A user is asking about the database contents. Use the provided database information to give a comprehensive, helpful answer.

USER QUESTION: {query}

{context}

Please provide a detailed response that:
1. Directly answers the user's question
2. References specific tables, columns, or data structures from the context
3. Explains how the information relates to AML compliance and monitoring
4. Suggests additional related tables or analysis if relevant
5. Uses clear, professional language

RESPONSE:"""

        try:
            # Use the LLM manager to get a response - fix method name
            if hasattr(llm_manager, 'complete'):
                response = llm_manager.complete(prompt, max_tokens=500)
            elif hasattr(llm_manager, 'generate_text'):
                response = llm_manager.generate_text(prompt, max_tokens=500)
            else:
                response = None
            return response if response else self._generate_fallback_response(query, context)
        except Exception as e:
            print(f"Error generating LLM response: {e}")
            return self._generate_fallback_response(query, context)
    
    def _generate_fallback_response(self, query: str, context: str) -> str:
        """Generate a fallback response when LLM is not available."""
        search_results = self.semantic_search(query, max_results=3)
        
        if not search_results:
            return f"I couldn't find specific information about '{query}' in the AML database. Please try a different question or be more specific about what you're looking for."
        
        response_parts = [f"Based on your question about '{query}', I found these relevant database elements:\n"]
        
        for i, result in enumerate(search_results, 1):
            metadata = result.get('metadata', {})
            table_name = metadata.get('table_name', 'Unknown')
            owner = metadata.get('owner', 'Unknown')
            
            response_parts.append(f"{i}. **{owner}.{table_name}** (Similarity: {result['similarity']:.1%})")
            response_parts.append(f"   This table contains: {result['content'][:150]}...\n")
        
        response_parts.append("For more detailed analysis, please ask specific questions about these tables or their relationships.")
        
        return "\n".join(response_parts)
    
    def chat(self, user_input: str) -> str:
        """Process user input and generate response."""
        if not user_input.strip():
            return "Please ask a question about the AML database."
        
        # Add to conversation history
        self.conversation_history.append({"role": "user", "content": user_input})
        
        # Build context using semantic search
        context = self.build_context(user_input)
        
        # Generate response
        response = self.generate_response(user_input, context)
        
        # Add response to history
        self.conversation_history.append({"role": "assistant", "content": response})
        
        return response
    
    def show_conversation_history(self):
        """Display conversation history."""
        if not self.conversation_history:
            print("No conversation history yet.")
            return
        
        print("\n" + "="*60)
        print("CONVERSATION HISTORY")
        print("="*60)
        
        for i, message in enumerate(self.conversation_history):
            role = "USER" if message["role"] == "user" else "ASSISTANT"
            print(f"\n{role}: {message['content']}")
        print("="*60)

def main():
    """Main chat interface."""
    print("🏦 AML Database Chat Interface with BGE Semantic Search")
    print("="*60)
    
    # Initialize chat bot
    chatbot = AMLChatBot()
    chatbot.initialize()
    
    print("\n💬 Chat is ready! Ask questions about the AML database.")
    print("Commands:")
    print("  - Type your question and press Enter")
    print("  - 'history' - Show conversation history")
    print("  - 'help' - Show example questions")
    print("  - 'quit' or 'exit' - End chat")
    print("="*60)
    
    # Example questions
    example_questions = [
        "What customer information is available in the database?",
        "Show me tables related to transactions",
        "What data do we have for risk assessment?",
        "Are there any tables for suspicious activity monitoring?",
        "What payment-related information is stored?",
        "Show me AML compliance tables",
        "What account balance data is available?",
        "Are there tables for fraud detection?",
        "What transaction monitoring capabilities exist?",
        "Show me customer due diligence data"
    ]
    
    while True:
        try:
            user_input = input("\nYou: ").strip()
            
            if user_input.lower() in ['quit', 'exit', 'q']:
                print("Thank you for using the AML Database Chat! Goodbye!")
                break
            elif user_input.lower() == 'history':
                chatbot.show_conversation_history()
                continue
            elif user_input.lower() == 'help':
                print("\nExample questions you can ask:")
                for i, question in enumerate(example_questions, 1):
                    print(f"  {i}. {question}")
                continue
            elif not user_input:
                print("Please ask a question about the AML database.")
                continue
            
            # Process the question
            print("\nSearching database...")
            start_time = time.time()
            response = chatbot.chat(user_input)
            elapsed_time = time.time() - start_time
            
            print(f"\nAssistant (took {elapsed_time:.1f}s):")
            print(response)
            
        except KeyboardInterrupt:
            print("\n\nChat interrupted. Goodbye!")
            break
        except Exception as e:
            print(f"\nError: {e}")
            print("Please try again with a different question.")

if __name__ == "__main__":
    main()