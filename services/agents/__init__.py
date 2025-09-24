"""
Agent services package initialization.
Provides agentic behavior capabilities for the RAG system.
"""

__version__ = "1.0.0"

from .agentic_behavior import (
    AgentState,
    ConversationMemory,
    ConversationTurn,
    QueryRouter,
    SchemaRetriever,
    SQLGenerator,
    SQLExecutor,
    AnswerComposer
)

# Import orchestrator only if LangGraph is available
try:
    from .langgraph_orchestrator import AgentOrchestrator
    LANGGRAPH_AVAILABLE = True
except ImportError:
    LANGGRAPH_AVAILABLE = False
    AgentOrchestrator = None

__all__ = [
    "AgentState",
    "ConversationMemory", 
    "ConversationTurn",
    "QueryRouter",
    "SchemaRetriever",
    "SQLGenerator",
    "SQLExecutor",
    "AnswerComposer",
    "AgentOrchestrator",
    "LANGGRAPH_AVAILABLE"
]