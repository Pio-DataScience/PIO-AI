"""
Main answer generation function that orchestrates retrieval and LLM response.
"""

import sys
import os
from pathlib import Path
from typing import Dict, Any, Optional, List
from dataclasses import dataclass

# Add package to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from services.retriever.hybrid import retrieve, retrieve_with_classification
from services.retriever.pack_context import pack_context, format_context_for_llm
from services.llm.provider import chat, get_available_providers
from services.llm.prompt_templates import create_messages


@dataclass
class AnswerResponse:
    """Complete response with answer and metadata."""
    answer: str
    query: str
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


def answer_query(query: str, project: str, path: str = "", line: int = 0,
                max_context_tokens: int = 8000, max_results: int = 20,
                provider: Optional[str] = None, debug: bool = False) -> AnswerResponse:
    """
    Main function to answer user queries using RAG.
    
    Args:
        query: User's question
        project: Project name to search in
        path: Optional file path context
        line: Optional line number context
        max_context_tokens: Maximum tokens for context
        max_results: Maximum search results
        provider: LLM provider to use
        debug: Include debug information
        
    Returns:
        AnswerResponse with answer and metadata
    """
    import time
    
    start_time = time.time()
    
    try:
        # 1. Retrieve relevant context
        retrieval_start = time.time()
        hits, classification = retrieve_with_classification(
            query, project, path, line, max_results
        )
        retrieval_time = time.time() - retrieval_start
        
        # 2. Pack context for LLM
        packed_context = pack_context(hits, query, max_context_tokens)
        
        # 3. Format context for LLM
        formatted_context = format_context_for_llm(packed_context)
        
        # 4. Create prompt messages
        messages = create_messages(
            query, formatted_context, classification, project, path, line
        )
        
        # 5. Get LLM response
        llm_start = time.time()
        llm_response = chat(messages, provider=provider, temperature=0.1)
        llm_time = time.time() - llm_start
        
        # 6. Create response
        response = AnswerResponse(
            answer=llm_response.content,
            query=query,
            query_type=classification.query_type,
            project=project,
            context_summary=packed_context.summary,
            citations=packed_context.citations,
            tokens_used=llm_response.tokens_used,
            retrieval_time=retrieval_time,
            llm_time=llm_time,
            provider_used=llm_response.model,
            truncated=packed_context.truncated
        )
        
        # Add debug info if requested
        if debug:
            response.debug_info = {
                "classification": classification.__dict__,
                "search_hits": len(hits),
                "context_excerpts": len(packed_context.excerpts),
                "context_tokens": packed_context.total_tokens,
                "total_time": time.time() - start_time,
                "available_providers": get_available_providers(),
                "llm_metadata": llm_response.metadata
            }
        
        return response
        
    except Exception as e:
        # Return error response
        return AnswerResponse(
            answer=f"Sorry, I encountered an error while processing your query: {str(e)}",
            query=query,
            query_type="error",
            project=project,
            context_summary="Error occurred during processing",
            citations=[],
            debug_info={"error": str(e)} if debug else None
        )


def answer_simple(query: str, project: str) -> str:
    """
    Simple interface that returns just the answer text.
    
    Args:
        query: User's question  
        project: Project to search in
        
    Returns:
        Answer text
    """
    response = answer_query(query, project)
    return response.answer


def answer_with_context(query: str, project: str, path: str = "", line: int = 0) -> Dict[str, Any]:
    """
    Answer with additional context information.
    
    Args:
        query: User's question
        project: Project to search in
        path: Optional file path
        line: Optional line number
        
    Returns:
        Dict with answer, citations, and metadata
    """
    response = answer_query(query, project, path, line, debug=True)
    
    return {
        "answer": response.answer,
        "query_type": response.query_type,
        "citations": response.citations,
        "context_summary": response.context_summary,
        "tokens_used": response.tokens_used,
        "retrieval_time": response.retrieval_time,
        "llm_time": response.llm_time,
        "provider": response.provider_used,
        "truncated": response.truncated,
        "debug": response.debug_info
    }


def format_answer_for_display(response: AnswerResponse, include_metadata: bool = True) -> str:
    """
    Format answer response for display in CLI or web interface.
    
    Args:
        response: AnswerResponse to format
        include_metadata: Whether to include metadata
        
    Returns:
        Formatted string
    """
    lines = []
    
    # Main answer
    lines.append("# Answer")
    lines.append("")
    lines.append(response.answer)
    lines.append("")
    
    # Citations
    if response.citations and include_metadata:
        lines.append("## Sources")
        for citation in response.citations:
            lines.append(f"- {citation}")
        lines.append("")
    
    # Metadata
    if include_metadata:
        lines.append("## Query Info")
        lines.append(f"- Type: {response.query_type}")
        lines.append(f"- Project: {response.project}")
        
        if response.tokens_used:
            lines.append(f"- Tokens used: {response.tokens_used}")
        
        if response.retrieval_time and response.llm_time:
            total_time = response.retrieval_time + response.llm_time
            lines.append(f"- Time: {total_time:.2f}s (retrieval: {response.retrieval_time:.2f}s, LLM: {response.llm_time:.2f}s)")
        
        if response.provider_used:
            lines.append(f"- Provider: {response.provider_used}")
        
        if response.truncated:
            lines.append("- ⚠️ Context was truncated due to length limits")
        
        lines.append("")
        lines.append(f"Context: {response.context_summary}")
    
    return "\n".join(lines)


# Convenience functions for common patterns
def ask_about_line(path: str, line: int, question: str, project: str) -> str:
    """Ask a question about a specific line of code."""
    return answer_simple(f"In {path} at line {line}: {question}", project)


def ask_about_function(function_name: str, project: str) -> str:
    """Ask about a specific function."""
    return answer_simple(f"Tell me about the function {function_name}", project)


def ask_about_class(class_name: str, project: str) -> str:
    """Ask about a specific class."""
    return answer_simple(f"Tell me about the class {class_name}", project)


def ask_about_file(file_path: str, project: str) -> str:
    """Ask about a specific file."""
    return answer_simple(f"What does the file {file_path} do?", project)


def ask_about_schema(table_name: str, project: str) -> str:
    """Ask about a database table."""
    return answer_simple(f"Tell me about the database table {table_name}", project)