"""
Intelligent Query Reformulator for Vector Database Retrieval.
Transforms natural language queries into optimized retrieval queries with memory awareness.
"""

import logging
import re
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass
from enum import Enum

logger = logging.getLogger(__name__)


class QueryIntent(Enum):
    """Types of query intents."""
    TABLE_METADATA = "table_metadata"  # General info about table
    COLUMN_DETAILS = "column_details"  # Specific column information
    COLUMN_LIST = "column_list"  # List all columns
    TABLE_PURPOSE = "table_purpose"  # Business purpose
    TABLE_RELATIONSHIPS = "table_relationships"  # Foreign keys, joins
    DATA_QUERY = "data_query"  # Actual data retrieval
    FOLLOW_UP = "follow_up"  # Follow-up question
    GENERAL = "general"  # General question


@dataclass
class RetrievalQuery:
    """Optimized query for vector database."""
    original_query: str
    reformulated_query: str
    intent: QueryIntent
    target_table: Optional[str]
    target_columns: List[str]
    should_retrieve_complete_metadata: bool
    search_scope: str  # "table", "column", "all"
    confidence: float
    
    
class ConversationContext:
    """Maintains conversation context for follow-up questions."""
    
    def __init__(self):
        """Initialize conversation context."""
        self.last_table: Optional[str] = None
        self.last_columns: List[str] = []
        self.last_intent: Optional[QueryIntent] = None
        self.mentioned_entities: List[str] = []
        self.turn_count: int = 0
    
    def update(self, table: Optional[str], columns: List[str], intent: QueryIntent):
        """Update context with new information."""
        if table:
            self.last_table = table
            if table not in self.mentioned_entities:
                self.mentioned_entities.append(table)
        
        if columns:
            self.last_columns = columns
            for col in columns:
                if col not in self.mentioned_entities:
                    self.mentioned_entities.append(col)
        
        self.last_intent = intent
        self.turn_count += 1
    
    def is_follow_up(self, query: str) -> bool:
        """Determine if query is a follow-up."""
        # Only detect as follow-up if we have prior context
        if not self.last_table:
            return False
            
        follow_up_patterns = [
            r'\b(those|that|these|them|it)\b',
            r'\b(more|other|additional|rest)\b',
            r'\b(no|but|actually|check|sure|verify)\b',
        ]
        
        query_lower = query.lower()
        return any(re.search(pattern, query_lower) for pattern in follow_up_patterns)
    
    def clear(self):
        """Clear context (e.g., on topic change)."""
        self.last_table = None
        self.last_columns = []
        self.last_intent = None
        self.turn_count = 0
        self.mentioned_entities = []


class IntelligentQueryReformulator:
    """
    Reformulates natural language queries into optimized vector database queries.
    Maintains conversation context and understands user intent.
    """
    
    # Table name patterns
    TABLE_PATTERNS = [
        r'\b(PIO_[A-Z_]+)\b',
        r'\b([A-Z][A-Z_]{3,})\b',
        r'\btable\s+(\w+)',
        r'(\w+)\s+table',
    ]
    
    # Column name patterns
    COLUMN_PATTERNS = [
        r'\bcolumn[s]?\s+(\w+)',
        r'(\w+)\s+column',
        r'\bfield[s]?\s+(\w+)',
    ]
    
    # Intent patterns
    INTENT_PATTERNS = {
        QueryIntent.TABLE_METADATA: [
            r'what is.*table.*about',
            r'describe.*table',
            r'tell me about.*table',
            r'information about.*table',
            r'details? (?:of|about|for).*table',
            r'table.*metadata',
            r'table.*structure',
            r'table.*information',
        ],
        QueryIntent.COLUMN_LIST: [
            r'list.*columns?',
            r'what columns?',
            r'show.*columns?',
            r'all columns?',
            r'how many columns?',
            r'column.*list',
            r'columns? (?:in|of|for)',
        ],
        QueryIntent.COLUMN_DETAILS: [
            r'what is.*column',
            r'describe.*column',
            r'column.*(?:type|meaning|purpose)',
            r'tell me about.*column',
        ],
        QueryIntent.TABLE_PURPOSE: [
            r'purpose of.*table',
            r'table.*used for',
            r'why.*table',
            r'business.*purpose',
        ],
        QueryIntent.TABLE_RELATIONSHIPS: [
            r'related? tables?',
            r'foreign keys?',
            r'relationships?',
            r'joins?',
            r'connected tables?',
        ]
    }
    
    def __init__(self):
        """Initialize reformulator."""
        self.context = ConversationContext()
        
        # Compile patterns
        self.compiled_table_patterns = [re.compile(p, re.IGNORECASE) for p in self.TABLE_PATTERNS]
        self.compiled_column_patterns = [re.compile(p, re.IGNORECASE) for p in self.COLUMN_PATTERNS]
        
        self.compiled_intent_patterns = {}
        for intent, patterns in self.INTENT_PATTERNS.items():
            self.compiled_intent_patterns[intent] = [
                re.compile(p, re.IGNORECASE) for p in patterns
            ]
        
        logger.info("Intelligent query reformulator initialized")
    
    def reformulate(self, query: str, session_id: Optional[str] = None) -> RetrievalQuery:
        """
        Reformulate query for optimal vector database retrieval.
        
        Args:
            query: Natural language query
            session_id: Session identifier for context
            
        Returns:
            RetrievalQuery with optimized search parameters
        """
        # Extract entities first
        table_name = self._extract_table_name(query)
        column_names = self._extract_column_names(query)
        
        # Check if follow-up BEFORE intent detection
        is_follow_up = self.context.is_follow_up(query)
        
        # Use context for follow-ups when no clear table extracted
        if is_follow_up and not table_name and self.context.last_table:
            table_name = self.context.last_table
            logger.info(f"Follow-up detected, using context table: {table_name}")
        elif is_follow_up and table_name and table_name != self.context.last_table:
            # If follow-up but extracted different table, it's likely wrong extraction
            # Stick with context table for follow-up questions
            if self.context.last_table:
                logger.info(f"Follow-up with conflicting table extraction, using context: {self.context.last_table}")
                table_name = self.context.last_table
        
        # Detect intent
        intent = self._detect_intent(query, is_follow_up)
        
        # Determine if complete metadata needed
        needs_complete_metadata = self._needs_complete_metadata(intent, query)
        
        # Build reformulated query
        reformulated = self._build_reformulated_query(
            query, intent, table_name, column_names, is_follow_up
        )
        
        # Determine search scope
        search_scope = self._determine_search_scope(intent, table_name, column_names)
        
        # Update context
        self.context.update(table_name, column_names, intent)
        
        # Calculate confidence
        confidence = self._calculate_confidence(table_name, intent, is_follow_up)
        
        retrieval_query = RetrievalQuery(
            original_query=query,
            reformulated_query=reformulated,
            intent=intent,
            target_table=table_name,
            target_columns=column_names,
            should_retrieve_complete_metadata=needs_complete_metadata,
            search_scope=search_scope,
            confidence=confidence
        )
        
        logger.info(
            f"Query reformulated: '{query[:50]}...' -> '{reformulated[:50]}...'",
            extra={
                "intent": intent.value,
                "table": table_name,
                "complete_metadata": needs_complete_metadata,
                "is_follow_up": is_follow_up
            }
        )
        
        return retrieval_query
    
    def _extract_table_name(self, query: str) -> Optional[str]:
        """Extract table name from query."""
        # Try each pattern in order
        for pattern in self.compiled_table_patterns:
            matches = pattern.findall(query)
            for match in matches:
                if isinstance(match, tuple):
                    match = match[0] if match else None
                if match:
                    table_name = match.upper()
                    # Validate it looks like a table name (not common words)
                    if len(table_name) > 3 and table_name not in ['WHAT', 'SHOW', 'TELL', 'THIS', 'THAT', 'THOSE', 'THESE']:
                        return table_name
        return None
    
    def _extract_column_names(self, query: str) -> List[str]:
        """Extract column names from query."""
        columns = []
        for pattern in self.compiled_column_patterns:
            matches = pattern.findall(query)
            for match in matches:
                if isinstance(match, tuple):
                    match = match[0]
                columns.append(match.upper())
        return columns
    
    def _detect_intent(self, query: str, is_follow_up: bool) -> QueryIntent:
        """Detect query intent."""
        query_lower = query.lower()
        
        # Match against intent patterns FIRST (before follow-up check)
        # This ensures clear intent queries are classified properly
        for intent, patterns in self.compiled_intent_patterns.items():
            for pattern in patterns:
                if pattern.search(query_lower):
                    return intent
        
        # Check for follow-up AFTER pattern matching
        if is_follow_up:
            # Inherit or refine intent from context
            if self.context.last_intent == QueryIntent.TABLE_METADATA:
                # Follow-up on table usually wants more details
                if any(word in query_lower for word in ['column', 'field', 'more']):
                    return QueryIntent.COLUMN_LIST
            return QueryIntent.FOLLOW_UP
        
        # Check for data query
        if any(word in query_lower for word in ['show', 'select', 'get', 'find', 'retrieve']):
            if 'where' in query_lower or 'with' in query_lower:
                return QueryIntent.DATA_QUERY
        
        # Default to general metadata request
        return QueryIntent.TABLE_METADATA
    
    def _needs_complete_metadata(self, intent: QueryIntent, query: str) -> bool:
        """Determine if complete metadata should be retrieved."""
        # These intents need complete table metadata, not just samples
        complete_metadata_intents = {
            QueryIntent.TABLE_METADATA,
            QueryIntent.COLUMN_LIST,
        }
        
        if intent in complete_metadata_intents:
            return True
        
        # Check for keywords indicating need for complete info
        complete_keywords = ['all', 'complete', 'full', 'total', 'how many', 'list']
        query_lower = query.lower()
        
        return any(keyword in query_lower for keyword in complete_keywords)
    
    def _build_reformulated_query(
        self,
        query: str,
        intent: QueryIntent,
        table_name: Optional[str],
        column_names: List[str],
        is_follow_up: bool
    ) -> str:
        """Build optimized query for vector database."""
        
        # For complete metadata, use table-specific query
        if intent == QueryIntent.TABLE_METADATA and table_name:
            return f"table {table_name} complete metadata structure columns count"
        
        if intent == QueryIntent.COLUMN_LIST and table_name:
            return f"table {table_name} all columns list complete structure"
        
        if intent == QueryIntent.COLUMN_DETAILS and column_names and table_name:
            cols = ' '.join(column_names)
            return f"table {table_name} column {cols} definition type description"
        
        if intent == QueryIntent.TABLE_PURPOSE and table_name:
            return f"table {table_name} business purpose description usage"
        
        if intent == QueryIntent.TABLE_RELATIONSHIPS and table_name:
            return f"table {table_name} foreign key relationship connected tables"
        
        # For follow-ups, use context
        if is_follow_up and self.context.last_table:
            table = self.context.last_table
            return f"table {table} additional information columns metadata"
        
        # Default: clean up the query
        return self._clean_query(query)
    
    def _clean_query(self, query: str) -> str:
        """Clean query by removing conversational elements."""
        # Remove question words at start
        cleaned = re.sub(r'^(what|how|which|when|where|why|tell me|show me)\s+', '', query, flags=re.IGNORECASE)
        
        # Remove filler words
        filler_words = ['is', 'are', 'the', 'a', 'an', 'about', 'of', 'for']
        words = cleaned.split()
        cleaned_words = [w for w in words if w.lower() not in filler_words]
        
        return ' '.join(cleaned_words)
    
    def _determine_search_scope(
        self,
        intent: QueryIntent,
        table_name: Optional[str],
        column_names: List[str]
    ) -> str:
        """Determine what to search for."""
        if column_names:
            return "column"
        if table_name:
            return "table"
        return "all"
    
    def _calculate_confidence(
        self,
        table_name: Optional[str],
        intent: QueryIntent,
        is_follow_up: bool
    ) -> float:
        """Calculate confidence in reformulation."""
        confidence = 0.5
        
        if table_name:
            confidence += 0.3
        
        if intent != QueryIntent.GENERAL:
            confidence += 0.2
        
        if is_follow_up and self.context.last_table:
            confidence += 0.1
        
        return min(confidence, 1.0)
    
    def reset_context(self):
        """Reset conversation context."""
        self.context.clear()
        logger.info("Conversation context reset")
    
    def get_context_summary(self) -> Dict[str, Any]:
        """Get summary of current context."""
        return {
            "last_table": self.context.last_table,
            "last_columns": self.context.last_columns,
            "last_intent": self.context.last_intent.value if self.context.last_intent else None,
            "turn_count": self.context.turn_count,
            "mentioned_entities": self.context.mentioned_entities
        }
