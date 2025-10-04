"""
Comprehensive edge case handling with graceful degradation.
Handles missing resources, errors, and ambiguous scenarios.
"""

import logging
import re
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass
from enum import Enum
import random

logger = logging.getLogger(__name__)


class FallbackStrategy(Enum):
    """Fallback strategies for different failure modes."""
    ALTERNATIVE_METHOD = "alternative_method"
    DEGRADED_SERVICE = "degraded_service"
    USER_GUIDANCE = "user_guidance"
    CACHED_RESPONSE = "cached_response"
    ERROR_EXPLANATION = "error_explanation"


@dataclass
class EdgeCaseResult:
    """Result of edge case handling."""
    success: bool
    fallback_used: Optional[FallbackStrategy]
    response: str
    metadata: Dict[str, Any]
    suggestions: List[str]


class VectorIndexFallbackHandler:
    """Handle missing or unavailable vector indexes."""
    
    def __init__(self, catalog_db=None, bm25_retriever=None):
        """
        Initialize fallback handler.
        
        Args:
            catalog_db: Catalog database for text search
            bm25_retriever: BM25 keyword search fallback
        """
        self.catalog_db = catalog_db
        self.bm25_retriever = bm25_retriever
        self.fallback_available = catalog_db is not None or bm25_retriever is not None
        
        logger.info(
            "Vector fallback handler initialized",
            extra={
                "operation": "fallback.init",
                "has_catalog": catalog_db is not None,
                "has_bm25": bm25_retriever is not None
            }
        )
    
    def handle_missing_embeddings(
        self,
        query: str,
        error: Exception
    ) -> EdgeCaseResult:
        """
        Handle case where embeddings are unavailable.
        
        Args:
            query: User query
            error: Original error
            
        Returns:
            Fallback result
        """
        logger.warning(
            f"Vector embeddings unavailable: {error}",
            extra={
                "operation": "fallback.missing_embeddings",
                "query": query[:100],
                "error_type": type(error).__name__
            }
        )
        
        # Try BM25 fallback
        if self.bm25_retriever:
            try:
                results = self.bm25_retriever.search(query, k=10)
                
                response = (
                    "Vector search is currently unavailable, but I found these results "
                    "using keyword search:\n\n"
                )
                
                for i, result in enumerate(results[:5], 1):
                    response += f"{i}. {result.get('name', 'Unknown')}\n"
                
                return EdgeCaseResult(
                    success=True,
                    fallback_used=FallbackStrategy.ALTERNATIVE_METHOD,
                    response=response,
                    metadata={"method": "bm25", "result_count": len(results)},
                    suggestions=["Results are based on keyword matching only"]
                )
            except Exception as e:
                logger.error(f"BM25 fallback also failed: {e}")
        
        # Try catalog text search
        if self.catalog_db:
            try:
                # Simple SQL text search
                results = self._catalog_text_search(query)
                
                response = (
                    "Advanced search is temporarily unavailable. "
                    "Here are basic catalog results:\n\n"
                )
                
                for result in results[:5]:
                    response += f"- {result}\n"
                
                return EdgeCaseResult(
                    success=True,
                    fallback_used=FallbackStrategy.DEGRADED_SERVICE,
                    response=response,
                    metadata={"method": "catalog_text", "result_count": len(results)},
                    suggestions=["Try being more specific with table or column names"]
                )
            except Exception as e:
                logger.error(f"Catalog search failed: {e}")
        
        # No fallback available
        return EdgeCaseResult(
            success=False,
            fallback_used=FallbackStrategy.USER_GUIDANCE,
            response=(
                "I'm having trouble with semantic search right now. "
                "Please try:\n"
                "- Using specific table or column names\n"
                "- Asking about schema structure directly\n"
                "- Rephrasing your question with more keywords"
            ),
            metadata={"error": str(error)},
            suggestions=[
                "Try: 'Show me the structure of table X'",
                "Try: 'What columns are in the customer table?'"
            ]
        )
    
    def handle_dimension_mismatch(
        self,
        expected_dim: int,
        actual_dim: int
    ) -> EdgeCaseResult:
        """
        Handle embedding dimension mismatch.
        
        Args:
            expected_dim: Expected dimension
            actual_dim: Actual dimension
            
        Returns:
            Guidance result
        """
        logger.error(
            f"Embedding dimension mismatch: expected {expected_dim}, got {actual_dim}",
            extra={
                "operation": "fallback.dimension_mismatch",
                "expected": expected_dim,
                "actual": actual_dim
            }
        )
        
        response = (
            "The embedding system needs to be reconfigured. "
            "Database queries and schema information are still available through alternative methods."
        )
        
        return EdgeCaseResult(
            success=False,
            fallback_used=FallbackStrategy.DEGRADED_SERVICE,
            response=response,
            metadata={
                "expected_dim": expected_dim,
                "actual_dim": actual_dim,
                "requires_reembedding": True
            },
            suggestions=["Ask about specific tables or schemas by name"]
        )
    
    def _catalog_text_search(self, query: str) -> List[str]:
        """
        Simple text search in catalog database.
        
        Args:
            query: Search query
            
        Returns:
            List of matching items
        """
        # Simplified implementation - would use actual SQL query
        return []


class EmptyResultHandler:
    """Handle queries that return no results."""
    
    def __init__(self, schema_catalog=None):
        """
        Initialize handler.
        
        Args:
            schema_catalog: Schema catalog for suggestions
        """
        self.schema_catalog = schema_catalog
    
    def handle_empty_results(
        self,
        query: str,
        search_type: str
    ) -> EdgeCaseResult:
        """
        Generate helpful response for empty results.
        
        Args:
            query: Original query
            search_type: Type of search performed
            
        Returns:
            Guidance result
        """
        logger.info(
            f"No results found for query: {query[:100]}",
            extra={
                "operation": "fallback.empty_results",
                "query": query[:100],
                "search_type": search_type
            }
        )
        
        # Extract keywords from query
        keywords = self._extract_keywords(query)
        
        # Generate contextual suggestions
        suggestions = self._generate_suggestions(keywords)
        
        response = (
            f"I couldn't find specific information about '{query}'. "
            "This could mean:\n"
            "- The table/column doesn't exist in our database\n"
            "- The term is too broad or ambiguous\n"
            "- It's referred to by a different name\n\n"
            "Try these suggestions:\n"
        )
        
        for i, suggestion in enumerate(suggestions, 1):
            response += f"{i}. {suggestion}\n"
        
        return EdgeCaseResult(
            success=False,
            fallback_used=FallbackStrategy.USER_GUIDANCE,
            response=response,
            metadata={"keywords": keywords, "search_type": search_type},
            suggestions=suggestions
        )
    
    def _extract_keywords(self, query: str) -> List[str]:
        """Extract important keywords from query."""
        # Remove common words
        stop_words = {'the', 'a', 'an', 'is', 'are', 'what', 'how', 'show', 'me', 'tell'}
        words = re.findall(r'\b\w+\b', query.lower())
        return [w for w in words if w not in stop_words and len(w) > 2]
    
    def _generate_suggestions(self, keywords: List[str]) -> List[str]:
        """Generate contextual suggestions based on keywords."""
        suggestions = []
        
        # Check for common terms and suggest alternatives
        term_suggestions = {
            'customer': "Try 'customer data', 'KYC information', or 'client profiles'",
            'transaction': "Try 'transaction logs', 'payment data', or 'activity records'",
            'aml': "Try 'AML alerts', 'monitoring rules', or 'compliance reports'",
            'account': "Try 'account details', 'account types', or 'account relationships'"
        }
        
        for keyword in keywords:
            if keyword in term_suggestions:
                suggestions.append(term_suggestions[keyword])
        
        # Generic suggestions
        if not suggestions:
            suggestions = [
                "Ask about general topics like 'customers', 'transactions', or 'alerts'",
                "Request schema information: 'What tables are available?'",
                "Be more specific: 'Show me columns in the customer table'"
            ]
        
        return suggestions[:3]


class AmbiguousIntentHandler:
    """Handle ambiguous or unclear query intent."""
    
    CLARIFICATION_TEMPLATES = [
        "I want to make sure I understand correctly. Are you asking about {option1} or {option2}?",
        "Your question could relate to {option1} or {option2}. Which one interests you?",
        "Just to clarify: do you need {option1}, or {option2}?",
    ]
    
    def handle_ambiguous_intent(
        self,
        query: str,
        possible_intents: List[str],
        confidence_scores: Dict[str, float]
    ) -> EdgeCaseResult:
        """
        Handle ambiguous intent with clarification.
        
        Args:
            query: User query
            possible_intents: List of possible intents
            confidence_scores: Confidence for each intent
            
        Returns:
            Clarification result
        """
        logger.info(
            f"Ambiguous intent detected: {possible_intents}",
            extra={
                "operation": "fallback.ambiguous_intent",
                "query": query[:100],
                "intents": possible_intents,
                "confidences": confidence_scores
            }
        )
        
        # If confidence is very low for all, ask for clarification
        max_confidence = max(confidence_scores.values())
        
        if max_confidence < 0.4:
            # Too ambiguous - ask user
            intent_descriptions = {
                "schema": "information about database structure (tables, columns, relationships)",
                "data": "actual data from the database (query results)",
                "documentation": "documentation or descriptions",
                "general": "general information or help"
            }
            
            top_intents = sorted(
                possible_intents,
                key=lambda i: confidence_scores.get(i, 0),
                reverse=True
            )[:2]
            
            option1 = intent_descriptions.get(top_intents[0], top_intents[0])
            option2 = intent_descriptions.get(top_intents[1], top_intents[1]) if len(top_intents) > 1 else "something else"
            
            template = random.choice(self.CLARIFICATION_TEMPLATES)
            response = template.format(option1=option1, option2=option2)
            
            return EdgeCaseResult(
                success=False,
                fallback_used=FallbackStrategy.USER_GUIDANCE,
                response=response,
                metadata={"possible_intents": possible_intents, "confidences": confidence_scores},
                suggestions=[
                    f"Say '{option1}' if that's what you need",
                    f"Say '{option2}' if that's what you're looking for"
                ]
            )
        
        # Moderate confidence - proceed with best guess but mention it
        best_intent = max(confidence_scores.items(), key=lambda x: x[1])[0]
        
        response = f"I'm interpreting this as a question about {best_intent}. "
        
        return EdgeCaseResult(
            success=True,
            fallback_used=None,
            response=response,
            metadata={"chosen_intent": best_intent, "confidence": confidence_scores[best_intent]},
            suggestions=["Let me know if I misunderstood"]
        )


class SQLErrorHandler:
    """Handle SQL execution errors and timeouts."""
    
    def handle_sql_error(
        self,
        sql: str,
        error: Exception,
        error_type: str
    ) -> EdgeCaseResult:
        """
        Handle SQL execution error.
        
        Args:
            sql: Original SQL query
            error: Exception raised
            error_type: Type of error (syntax, timeout, permission, etc.)
            
        Returns:
            Error handling result
        """
        logger.error(
            f"SQL execution failed: {error_type}",
            extra={
                "operation": "fallback.sql_error",
                "error_type": error_type,
                "error": str(error),
                "sql": sql[:200]
            }
        )
        
        if error_type == "timeout":
            return self._handle_timeout(sql)
        elif error_type == "syntax":
            return self._handle_syntax_error(sql, error)
        elif error_type == "permission":
            return self._handle_permission_error(sql)
        else:
            return self._handle_generic_error(sql, error)
    
    def _handle_timeout(self, sql: str) -> EdgeCaseResult:
        """Handle query timeout."""
        response = (
            "The query is taking too long to execute. This could be because:\n"
            "- The dataset is very large\n"
            "- The query needs optimization\n"
            "- Database is under heavy load\n\n"
            "Would you like me to:\n"
            "1. Try a simpler version with limited results\n"
            "2. Sample the data instead of querying all of it\n"
            "3. Help you refine the query to be more specific"
        )
        
        return EdgeCaseResult(
            success=False,
            fallback_used=FallbackStrategy.USER_GUIDANCE,
            response=response,
            metadata={"error_type": "timeout", "sql": sql[:200]},
            suggestions=[
                "Try adding a LIMIT clause",
                "Ask for a sample instead: 'Show me a sample of...'",
                "Be more specific about date ranges or filters"
            ]
        )
    
    def _handle_syntax_error(self, sql: str, error: Exception) -> EdgeCaseResult:
        """Handle SQL syntax error."""
        response = (
            "I encountered an issue generating the SQL query. "
            "This might be due to complex requirements or database-specific syntax. "
            "Let me try a different approach."
        )
        
        return EdgeCaseResult(
            success=False,
            fallback_used=FallbackStrategy.ALTERNATIVE_METHOD,
            response=response,
            metadata={"error_type": "syntax", "error": str(error), "sql": sql[:200]},
            suggestions=[
                "Try rephrasing your question more simply",
                "Break down complex requests into smaller questions",
                "Ask about the table structure first"
            ]
        )
    
    def _handle_permission_error(self, sql: str) -> EdgeCaseResult:
        """Handle permission/access error."""
        response = (
            "I don't have permission to access that data. "
            "This system is configured with read-only access to approved tables only."
        )
        
        return EdgeCaseResult(
            success=False,
            fallback_used=FallbackStrategy.ERROR_EXPLANATION,
            response=response,
            metadata={"error_type": "permission", "sql": sql[:200]},
            suggestions=[
                "Ask about publicly available tables",
                "Request schema information instead of data"
            ]
        )
    
    def _handle_generic_error(self, sql: str, error: Exception) -> EdgeCaseResult:
        """Handle generic SQL error."""
        response = (
            "Something went wrong while retrieving the data. "
            "Would you like me to try a different approach?"
        )
        
        return EdgeCaseResult(
            success=False,
            fallback_used=FallbackStrategy.ERROR_EXPLANATION,
            response=response,
            metadata={"error_type": "generic", "error": str(error)},
            suggestions=[
                "Try rephrasing your question",
                "Ask for schema information first",
                "Be more specific about what you need"
            ]
        )


class MissingSchemaHandler:
    """Handle missing or unavailable schema metadata."""
    
    def __init__(self, db_inspector=None):
        """
        Initialize handler.
        
        Args:
            db_inspector: Database inspection utility
        """
        self.db_inspector = db_inspector
    
    def handle_missing_schema(
        self,
        table_name: str,
        allow_introspection: bool = True
    ) -> EdgeCaseResult:
        """
        Handle missing schema information.
        
        Args:
            table_name: Name of table with missing schema
            allow_introspection: Whether to allow live DB introspection
            
        Returns:
            Result with schema or guidance
        """
        logger.warning(
            f"Schema metadata not found for table: {table_name}",
            extra={
                "operation": "fallback.missing_schema",
                "table": table_name
            }
        )
        
        # Try live introspection if allowed
        if allow_introspection and self.db_inspector:
            try:
                schema_info = self.db_inspector.get_table_schema(table_name)
                
                response = (
                    f"I don't have cached metadata for '{table_name}', "
                    f"but I inspected the database and found:\n\n"
                    f"Columns: {', '.join(schema_info['columns'])}\n"
                    f"Primary Key: {schema_info.get('primary_key', 'Unknown')}"
                )
                
                return EdgeCaseResult(
                    success=True,
                    fallback_used=FallbackStrategy.ALTERNATIVE_METHOD,
                    response=response,
                    metadata={"table": table_name, "schema": schema_info},
                    suggestions=["This information is directly from the database"]
                )
            except Exception as e:
                logger.error(f"Schema introspection failed: {e}")
        
        # No schema available
        response = (
            f"I don't have information about the structure of '{table_name}'. "
            "This could mean:\n"
            "- The table doesn't exist\n"
            "- It's a new table not yet documented\n"
            "- It's in a different schema or database"
        )
        
        return EdgeCaseResult(
            success=False,
            fallback_used=FallbackStrategy.USER_GUIDANCE,
            response=response,
            metadata={"table": table_name},
            suggestions=[
                "Check the table name spelling",
                "Ask 'What tables are available?'",
                "Try searching for related tables"
            ]
        )


class EdgeCaseOrchestrator:
    """
    Central orchestrator for all edge case handling.
    """
    
    def __init__(
        self,
        vector_fallback: Optional[VectorIndexFallbackHandler] = None,
        empty_result_handler: Optional[EmptyResultHandler] = None,
        ambiguous_intent_handler: Optional[AmbiguousIntentHandler] = None,
        sql_error_handler: Optional[SQLErrorHandler] = None,
        missing_schema_handler: Optional[MissingSchemaHandler] = None
    ):
        """Initialize orchestrator with handlers."""
        self.vector_fallback = vector_fallback or VectorIndexFallbackHandler()
        self.empty_result_handler = empty_result_handler or EmptyResultHandler()
        self.ambiguous_intent_handler = ambiguous_intent_handler or AmbiguousIntentHandler()
        self.sql_error_handler = sql_error_handler or SQLErrorHandler()
        self.missing_schema_handler = missing_schema_handler or MissingSchemaHandler()
        
        logger.info("Edge case orchestrator initialized")
    
    def handle(
        self,
        case_type: str,
        **kwargs
    ) -> EdgeCaseResult:
        """
        Route to appropriate handler.
        
        Args:
            case_type: Type of edge case
            **kwargs: Case-specific parameters
            
        Returns:
            Handling result
        """
        handlers = {
            "missing_embeddings": lambda: self.vector_fallback.handle_missing_embeddings(
                kwargs.get("query"), kwargs.get("error")
            ),
            "dimension_mismatch": lambda: self.vector_fallback.handle_dimension_mismatch(
                kwargs.get("expected_dim"), kwargs.get("actual_dim")
            ),
            "empty_results": lambda: self.empty_result_handler.handle_empty_results(
                kwargs.get("query"), kwargs.get("search_type")
            ),
            "ambiguous_intent": lambda: self.ambiguous_intent_handler.handle_ambiguous_intent(
                kwargs.get("query"), kwargs.get("possible_intents"), kwargs.get("confidence_scores")
            ),
            "sql_error": lambda: self.sql_error_handler.handle_sql_error(
                kwargs.get("sql"), kwargs.get("error"), kwargs.get("error_type")
            ),
            "missing_schema": lambda: self.missing_schema_handler.handle_missing_schema(
                kwargs.get("table_name"), kwargs.get("allow_introspection", True)
            )
        }
        
        handler = handlers.get(case_type)
        if not handler:
            logger.error(f"Unknown edge case type: {case_type}")
            return EdgeCaseResult(
                success=False,
                fallback_used=FallbackStrategy.ERROR_EXPLANATION,
                response="An unexpected error occurred. Please try rephrasing your question.",
                metadata={"case_type": case_type},
                suggestions=[]
            )
        
        return handler()
