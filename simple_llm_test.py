"""
Simple AML Web Chat without sentence transformers for testing LLM integration
"""

import os
import sys
import time
import uvicorn
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, List
from pydantic import BaseModel
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

# Add package to path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

try:
    from services.llm.provider import LLMManager, get_available_providers
    print("✅ LLM services imported successfully")
except ImportError as e:
    print(f"❌ LLM import error: {e}")
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
    title="AML Database Chat API (Simple)",
    description="Simple chat interface for testing LLM integration",
    version="1.0.0"
)

# Global chat bot instance
chatbot = None

class SimpleChatBot:
    """Simple chat bot for testing LLM integration."""
    
    def __init__(self):
        # Initialize LLM manager safely
        try:
            self.llm_manager = LLMManager()
            print("✅ LLM Manager initialized")
        except Exception as e:
            print(f"⚠️ LLM Manager initialization failed: {e}")
            self.llm_manager = None
    
    def generate_response(self, query: str) -> str:
        """Generate LLM response."""
        providers = get_available_providers()
        print(f"🔧 Available providers: {providers}")
        
        if not providers:
            return "❌ No LLM providers available. Please check your configuration."
        
        # Build prompt for LLM
        prompt = f"""You are PIO AI, an expert AML database analyst. You MUST answer ONLY based on the specific database information that would be retrieved for this query. Since this is a test environment, provide a response explaining that you need actual database search results to give specific information.

USER QUESTION: {query}

CRITICAL INSTRUCTIONS:
1. Explain that you need specific database search results to provide accurate information
2. Do NOT provide general AML knowledge or assumptions about what might be in databases
3. Suggest that the user should ask for specific table or column information
4. Mention that in the full system, you would search the database and provide only information found in the results

TEST RESPONSE:"""

        try:
            response = None
            
            # Debug: Check LLM manager availability
            print(f"🤖 LLM Manager available: {self.llm_manager is not None}")
            
            # Try using LLM manager chat method
            if self.llm_manager:
                try:
                    messages = [{"role": "user", "content": prompt}]
                    print("📤 Sending request to LLM...")
                    llm_response = self.llm_manager.chat(messages)
                    
                    # Extract content from LLMResponse object
                    if hasattr(llm_response, 'content'):
                        response = llm_response.content
                        print(f"📥 LLM Response received: {len(response)} characters")
                    else:
                        response = str(llm_response)
                        print(f"📥 LLM Response (string): {len(response)} characters")
                        
                except Exception as llm_error:
                    print(f"❌ LLM Manager error: {llm_error}")
                    response = None
            
            # Fallback to direct Cohere if LLM manager fails
            if not response:
                print("🔄 Trying direct Cohere Chat API fallback...")
                try:
                    import cohere
                    import os
                    
                    api_key = os.getenv("COHERE_API_KEY")
                    print(f"🔑 Cohere API key available: {api_key is not None}")
                    if api_key:
                        co = cohere.Client(api_key)
                        chat_response = co.chat(
                            model='command-r',  # Use the supported model
                            message=prompt,
                            max_tokens=800,
                            temperature=0.7
                        )
                        response = chat_response.text
                        print(f"✅ Direct Cohere Chat response: {len(response)} characters")
                    else:
                        response = None
                except Exception as cohere_error:
                    print(f"❌ Cohere error: {cohere_error}")
                    response = None
            
            return response if response else f"I received your question: '{query}' but I'm having trouble with the LLM integration. This is a fallback response for testing purposes."
            
        except Exception as e:
            print(f"❌ Error generating LLM response: {e}")
            return f"Error processing your question: '{query}'. Please check the server logs."

# Chat endpoint
@app.post("/chat", response_model=ChatResponse)
async def chat_endpoint(message: ChatMessage):
    """Chat endpoint for testing LLM integration."""
    start_time = time.time()
    
    try:
        response = chatbot.generate_response(message.message)
        
        return ChatResponse(
            response=response,
            search_results=[],  # Empty for this test
            timestamp=datetime.now().isoformat(),
            processing_time=time.time() - start_time
        )
    except Exception as e:
        print(f"❌ Chat endpoint error: {e}")
        return ChatResponse(
            response=f"Error: {str(e)}",
            search_results=[],
            timestamp=datetime.now().isoformat(),
            processing_time=time.time() - start_time
        )

# Simple HTML interface
@app.get("/", response_class=HTMLResponse)
async def get_chat_interface():
    """Serve the chat interface."""
    html_content = """
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>PIO AI - LLM Test</title>
        <style>
            body { font-family: Arial, sans-serif; max-width: 800px; margin: 0 auto; padding: 20px; }
            .header { background: linear-gradient(135deg, #1e3c72, #2a5298); color: white; padding: 20px; border-radius: 10px; margin-bottom: 20px; }
            .chat-container { border: 1px solid #ddd; height: 400px; overflow-y: auto; padding: 15px; margin-bottom: 20px; }
            .input-area { display: flex; gap: 10px; }
            input[type="text"] { flex: 1; padding: 10px; border: 1px solid #ddd; border-radius: 5px; }
            button { padding: 10px 20px; background: #2a5298; color: white; border: none; border-radius: 5px; cursor: pointer; }
            .message { margin-bottom: 15px; padding: 10px; border-radius: 5px; }
            .user-message { background: #e3f2fd; text-align: right; }
            .bot-message { background: #f5f5f5; }
        </style>
    </head>
    <body>
        <div class="header">
            <h1>🤖 PIO AI - LLM Integration Test</h1>
            <p>Testing LLM integration without sentence transformers</p>
        </div>
        
        <div id="chat-container" class="chat-container">
            <div class="message bot-message">
                <strong>PIO AI:</strong> Hello! I'm testing the LLM integration. Ask me anything about AML or compliance!
            </div>
        </div>
        
        <div class="input-area">
            <input type="text" id="messageInput" placeholder="Ask about AML, compliance, or database topics..." onkeypress="handleKeyPress(event)">
            <button onclick="sendMessage()">Send</button>
        </div>

        <script>
            async function sendMessage() {
                const input = document.getElementById('messageInput');
                const message = input.value.trim();
                if (!message) return;

                // Add user message to chat
                addMessage(message, 'user');
                input.value = '';

                try {
                    const response = await fetch('/chat', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ message: message, max_results: 5 })
                    });

                    const data = await response.json();
                    addMessage(data.response, 'bot');
                } catch (error) {
                    addMessage('Error: ' + error.message, 'bot');
                }
            }

            function addMessage(text, sender) {
                const container = document.getElementById('chat-container');
                const messageDiv = document.createElement('div');
                messageDiv.className = `message ${sender}-message`;
                messageDiv.innerHTML = `<strong>${sender === 'user' ? 'You' : 'PIO AI'}:</strong> ${text}`;
                container.appendChild(messageDiv);
                container.scrollTop = container.scrollHeight;
            }

            function handleKeyPress(event) {
                if (event.key === 'Enter') {
                    sendMessage();
                }
            }
        </script>
    </body>
    </html>
    """
    return HTMLResponse(content=html_content)

# Initialize chatbot on startup
@app.on_event("startup")
async def startup_event():
    global chatbot
    chatbot = SimpleChatBot()

if __name__ == "__main__":
    print("🌐 Starting Simple AML Chat Interface...")
    print("📍 Open your browser and go to: http://localhost:8010")
    print("🔗 Or try: http://127.0.0.1:8010")
    
    uvicorn.run(
        app,
        host="127.0.0.1",
        port=8010,
        log_level="info"
    )