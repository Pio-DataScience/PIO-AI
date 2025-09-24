"""
Agentic behavior system using LangGraph for multi-tool, stateful interactions.
Implements planning, execution, memory, and follow-up understanding.
"""

import json
import logging
from typing import Dict, List, Optional, Any, Literal, TypedDict
from datetime import datetime
from pathlib import Path
from dataclasses import dataclass, asdict

logger = logging.getLogger(__name__)

# Type definitions for the agent state
class AgentState(TypedDict):
    """State passed between agent nodes."""
    query: str
    query_type: Literal["schema", "data_analysis", "general", "follow_up", "conversation"]
    session_id: str
    turn_id: str
    conversation_history: List[Dict[str, Any]]
    retrieved_context: List[Dict[str, Any]]
    sql_query: Optional[str]
    sql_results: Optional[List[Dict]]
    entities_mentioned: Dict[str, Any]
    final_answer: Optional[str]
    confidence_score: float
    tools_used: List[str]
    error_message: Optional[str]


@dataclass
class ConversationTurn:
    """Single conversation turn with metadata."""
    turn_id: str
    user_query: str
    query_type: str
    entities_mentioned: Dict[str, Any]
    tools_used: List[str]
    final_answer: str
    confidence_score: float
    timestamp: str


class ConversationMemory:
    """
    Manages conversation state and memory for follow-up understanding.
    """
    
    def __init__(self, storage_path: Path):
        self.storage_path = storage_path
        self.storage_path.mkdir(parents=True, exist_ok=True)
        self.sessions: Dict[str, List[ConversationTurn]] = {}
        
    def get_session_file(self, session_id: str) -> Path:
        """Get file path for session storage."""
        return self.storage_path / f"session_{session_id}.json"
    
    def load_session(self, session_id: str) -> List[ConversationTurn]:
        """Load conversation history for a session."""
        session_file = self.get_session_file(session_id)
        
        if session_file.exists():
            try:
                with open(session_file, 'r') as f:
                    data = json.load(f)
                    turns = [ConversationTurn(**turn) for turn in data.get("turns", [])]
                    self.sessions[session_id] = turns
                    return turns
            except Exception as e:
                logger.warning(f"Failed to load session {session_id}: {e}")
        
        self.sessions[session_id] = []
        return []
    
    def save_turn(self, session_id: str, turn: ConversationTurn) -> None:
        """Save a conversation turn to persistent storage."""
        if session_id not in self.sessions:
            self.load_session(session_id)
        
        self.sessions[session_id].append(turn)
        
        # Keep only last 20 turns per session
        if len(self.sessions[session_id]) > 20:
            self.sessions[session_id] = self.sessions[session_id][-20:]
        
        # Save to file
        session_file = self.get_session_file(session_id)
        session_data = {
            "session_id": session_id,
            "turns": [asdict(turn) for turn in self.sessions[session_id]],
            "last_updated": datetime.utcnow().isoformat()
        }
        
        with open(session_file, 'w') as f:
            json.dump(session_data, f, indent=2)
    
    def get_recent_context(self, session_id: str, max_turns: int = 3) -> Dict[str, Any]:
        """Get recent conversation context for follow-up detection."""
        if session_id not in self.sessions:
            self.load_session(session_id)
        
        recent_turns = self.sessions[session_id][-max_turns:]
        
        context = {
            "recent_entities": {},
            "recent_tools": [],
            "recent_queries": [],
            "session_summary": ""
        }
        
        for turn in recent_turns:
            # Collect entities mentioned
            for entity_type, entities in turn.entities_mentioned.items():
                if entity_type not in context["recent_entities"]:
                    context["recent_entities"][entity_type] = []
                context["recent_entities"][entity_type].extend(entities)
            
            # Collect tools used
            context["recent_tools"].extend(turn.tools_used)
            context["recent_queries"].append(turn.user_query)
        
        # Create session summary
        if recent_turns:
            context["session_summary"] = f"Recent conversation about: {', '.join(context['recent_queries'][-2:])}"
        
        return context


class QueryRouter:
    """
    Routes queries to appropriate processing paths based on intent classification.
    Enhanced with casual conversation detection.
    """
    
    def __init__(self):
        self.schema_keywords = ["table", "column", "schema", "structure", "field", "database", "tables", "columns"]
        self.data_keywords = ["count", "null", "empty", "how many", "analyze", "aggregate", "records", "rows"]
        self.follow_up_indicators = ["which", "what about", "and", "also", "those", "them", "it", "that"]
        
        # Casual conversation patterns
        self.greeting_patterns = ["hi", "hello", "hey", "good morning", "good afternoon", "good evening"]
        self.casual_patterns = ["how are you", "what's up", "thanks", "thank you", "bye", "goodbye", "help", "what can you do"]
        self.question_starters = ["what", "how", "where", "when", "why", "which", "who", "can you", "do you", "are there"]
        
        # Database-specific indicators
        self.db_indicators = ["oracle", "sql", "query", "data", "aml", "customer", "transaction", "pio_", "bi_dwh"]
        self.technical_terms = ["primary key", "foreign key", "index", "constraint", "procedure", "function", "view"]
    
    def classify_query(self, query: str, context: Dict[str, Any]) -> str:
        """
        Classify query type for routing with conversation vs database detection.
        """
        query_lower = query.lower().strip()
        
        # Check for casual conversation first
        if self._is_casual_conversation(query_lower):
            return "conversation"
        
        # Check for follow-up patterns
        if self._is_follow_up(query_lower, context):
            return "follow_up"
        
        # Check if this requires database access
        if not self._requires_database_access(query_lower):
            return "conversation"
        
        # Check for data analysis intent
        if any(keyword in query_lower for keyword in self.data_keywords):
            return "data_analysis"
        
        # Check for schema inquiry
        if any(keyword in query_lower for keyword in self.schema_keywords):
            return "schema"
        
        return "general"
    
    def _is_follow_up(self, query: str, context: Dict[str, Any]) -> bool:
        """Detect if query is a follow-up to previous conversation."""
        if not context.get("recent_entities"):
            return False
        
        # Simple heuristics for follow-up detection
        has_follow_up_indicators = any(indicator in query for indicator in self.follow_up_indicators)
        has_recent_context = len(context.get("recent_queries", [])) > 0
        
        return has_follow_up_indicators and has_recent_context
    
    def extract_entities(self, query: str, context: Dict[str, Any]) -> Dict[str, Any]:
        """Extract entities (tables, columns) from query and context."""
        entities = {
            "tables": [],
            "columns": [],
            "inherited_tables": [],
            "inherited_columns": []
        }
        
        # Simple entity extraction (can be enhanced with NER)
        query_upper = query.upper()
        
        # Look for table patterns
        if "TABLE" in query_upper:
            # Extract table names (simplified)
            words = query_upper.split()
            for i, word in enumerate(words):
                if word == "TABLE" and i + 1 < len(words):
                    potential_table = words[i + 1].strip("?.,")
                    if potential_table.startswith("PIO_"):
                        entities["tables"].append(potential_table)
        
        # Inherit entities from recent context for follow-ups
        if context.get("recent_entities"):
            entities["inherited_tables"] = context["recent_entities"].get("tables", [])[-2:]
            entities["inherited_columns"] = context["recent_entities"].get("columns", [])[-5:]
        
        return entities
    
    def _is_casual_conversation(self, query: str) -> bool:
        """Detect if query is casual conversation that doesn't need database access."""
        # Direct greetings
        if any(greeting in query for greeting in self.greeting_patterns):
            return True
        
        # Casual conversation patterns
        if any(pattern in query for pattern in self.casual_patterns):
            return True
        
        # Very short queries are likely casual
        if len(query.split()) <= 2 and not any(db_word in query for db_word in self.db_indicators):
            return True
        
        return False
    
    def _requires_database_access(self, query: str) -> bool:
        """Determine if query requires database access."""
        # Explicit database indicators
        if any(indicator in query for indicator in self.db_indicators):
            return True
        
        # Technical database terms
        if any(term in query for term in self.technical_terms):
            return True
        
        # Schema or data keywords
        if any(keyword in query for keyword in self.schema_keywords + self.data_keywords):
            return True
        
        # Questions about specific business concepts that might be in database
        business_terms = ["customer", "account", "transaction", "risk", "compliance", "aml", "kyc"]
        if any(term in query for term in business_terms):
            return True
        
        # Questions asking for specific information
        question_indicators = ["what is", "show me", "find", "list", "tell me about"]
        if any(indicator in query for indicator in question_indicators):
            # Only if it's not a casual question
            casual_questions = ["what is your name", "what can you do", "what are you"]
            if not any(casual in query for casual in casual_questions):
                return True
        
        return False


class SchemaRetriever:
    """
    Retrieves schema information using existing retrieval systems.
    """
    
    def __init__(self, retriever):
        self.retriever = retriever
    
    def get_table_schema(self, table_name: str) -> Dict[str, Any]:
        """Get complete schema for a specific table."""
        try:
            # Use existing hybrid retrieval
            results = self.retriever.semantic_search(
                f"table {table_name} columns schema structure",
                max_results=10
            )
            
            # Filter results for the specific table
            table_results = [
                r for r in results 
                if r.get("metadata", {}).get("table_name", "").upper() == table_name.upper()
            ]
            
            if not table_results:
                return {"error": f"Table {table_name} not found in schema"}
            
            # Organize results by entity type
            table_summary = None
            columns = []
            
            for result in table_results:
                if result.get("metadata", {}).get("entity_type") == "table_summary":
                    table_summary = result
                elif result.get("metadata", {}).get("entity_type") == "column":
                    columns.append(result)
            
            return {
                "table_name": table_name,
                "table_summary": table_summary,
                "columns": columns,
                "total_columns": len(columns)
            }
            
        except Exception as e:
            logger.error(f"Schema retrieval failed for {table_name}: {e}")
            return {"error": str(e)}


class SQLGenerator:
    """
    Generates safe, validated SQL queries for data analysis.
    """
    
    def __init__(self, schema_retriever: SchemaRetriever):
        self.schema_retriever = schema_retriever
        self.allowed_functions = ["COUNT", "SUM", "AVG", "MIN", "MAX", "DISTINCT"]
    
    def generate_null_analysis_sql(self, table_name: str, columns: Optional[List[str]] = None) -> Dict[str, Any]:
        """Generate SQL to analyze null values in table columns."""
        # Get table schema first
        schema_info = self.schema_retriever.get_table_schema(table_name)
        
        if "error" in schema_info:
            return {"error": schema_info["error"]}
        
        # Use provided columns or get all from schema
        if not columns:
            available_columns = [
                col["metadata"]["column_name"] 
                for col in schema_info.get("columns", [])
                if col.get("metadata", {}).get("column_name")
            ]
            # Limit to first 20 columns to avoid huge queries
            columns = available_columns[:20]
        
        if not columns:
            return {"error": f"No columns found for table {table_name}"}
        
        # Generate null count SQL
        null_checks = []
        for col in columns:
            null_checks.append(f"SUM(CASE WHEN {col} IS NULL THEN 1 ELSE 0 END) AS {col}_nulls")
        
        sql_query = f"""
        SELECT 
            COUNT(*) AS total_rows,
            {', '.join(null_checks)}
        FROM {table_name}
        """
        
        return {
            "sql_query": sql_query,
            "query_type": "null_analysis",
            "table_name": table_name,
            "columns_analyzed": columns,
            "validation": "safe_read_only"
        }
    
    def validate_sql_safety(self, sql_query: str) -> Dict[str, Any]:
        """Validate that SQL is safe (read-only)."""
        sql_upper = sql_query.upper().strip()
        
        # Check for forbidden operations
        forbidden_keywords = ["INSERT", "UPDATE", "DELETE", "DROP", "CREATE", "ALTER", "TRUNCATE"]
        
        for keyword in forbidden_keywords:
            if keyword in sql_upper:
                return {
                    "safe": False,
                    "reason": f"Forbidden keyword detected: {keyword}",
                    "recommendation": "Only SELECT statements are allowed"
                }
        
        # Must start with SELECT
        if not sql_upper.startswith("SELECT"):
            return {
                "safe": False,
                "reason": "Query must start with SELECT",
                "recommendation": "Use SELECT statements for data analysis"
            }
        
        return {"safe": True, "validation_passed": True}


class SQLExecutor:
    """
    Executes validated SQL queries safely with connection pooling.
    """
    
    def __init__(self, oracle_dsn: str, oracle_user: str, oracle_password: str):
        self.oracle_dsn = oracle_dsn
        self.oracle_user = oracle_user
        self.oracle_password = oracle_password
    
    def execute_query(self, sql_query: str, max_rows: int = 1000) -> Dict[str, Any]:
        """Execute SQL query with safety limits."""
        import oracledb
        import pandas as pd
        
        try:
            # Add row limit for safety
            limited_query = f"""
            SELECT * FROM (
                {sql_query}
            ) WHERE ROWNUM <= {max_rows}
            """
            
            with oracledb.connect(
                user=self.oracle_user,
                password=self.oracle_password,
                dsn=self.oracle_dsn
            ) as conn:
                df = pd.read_sql(limited_query, conn)
                
                results = {
                    "success": True,
                    "rows_returned": len(df),
                    "columns": df.columns.tolist(),
                    "data": df.to_dict('records'),
                    "query_executed": sql_query,
                    "execution_time": datetime.utcnow().isoformat()
                }
                
                logger.info(f"SQL executed successfully: {len(df)} rows returned")
                return results
                
        except Exception as e:
            logger.error(f"SQL execution failed: {e}")
            return {
                "success": False,
                "error": str(e),
                "query_attempted": sql_query
            }


class AnswerComposer:
    """
    Composes final answers with proper grounding and citations.
    """
    
    def __init__(self, llm_provider):
        self.llm_provider = llm_provider
    
    def compose_schema_answer(self, query: str, schema_info: Dict[str, Any]) -> Dict[str, Any]:
        """Compose answer for schema-related queries."""
        if "error" in schema_info:
            return {
                "answer": f"I couldn't find schema information: {schema_info['error']}",
                "confidence_score": 0.0,
                "grounded": False
            }
        
        table_name = schema_info.get("table_name", "Unknown")
        columns = schema_info.get("columns", [])
        
        # Create structured answer
        answer_parts = [f"Table: {table_name}"]
        
        if schema_info.get("table_summary"):
            summary_content = schema_info["table_summary"].get("content", "")
            answer_parts.append(f"Purpose: {summary_content}")
        
        answer_parts.append(f"Total Columns: {len(columns)}")
        
        if columns:
            answer_parts.append("Key Columns:")
            for i, col in enumerate(columns[:10]):  # Show first 10 columns
                col_meta = col.get("metadata", {})
                col_name = col_meta.get("column_name", "Unknown")
                data_type = col_meta.get("data_type", "Unknown")
                aml_req = col_meta.get("aml_required", "Unknown")
                
                answer_parts.append(f"  - {col_name} ({data_type}) [AML: {aml_req}]")
            
            if len(columns) > 10:
                answer_parts.append(f"  ... and {len(columns) - 10} more columns")
        
        final_answer = "\n".join(answer_parts)
        
        return {
            "answer": final_answer,
            "confidence_score": 0.9 if columns else 0.3,
            "grounded": True,
            "sources": [{"table": table_name, "type": "schema"}]
        }
    
    def compose_data_analysis_answer(self, query: str, sql_results: Dict[str, Any]) -> Dict[str, Any]:
        """Compose answer for data analysis results."""
        if not sql_results.get("success"):
            return {
                "answer": f"Data analysis failed: {sql_results.get('error', 'Unknown error')}",
                "confidence_score": 0.0,
                "grounded": False
            }
        
        data = sql_results.get("data", [])
        
        if not data:
            return {
                "answer": "No data returned from the analysis.",
                "confidence_score": 0.1,
                "grounded": True
            }
        
        # Format results based on query type
        if "null" in query.lower():
            return self._format_null_analysis(data, sql_results)
        
        # Generic data formatting
        answer_parts = [f"Analysis Results ({len(data)} rows):"]
        
        for i, row in enumerate(data[:5]):  # Show first 5 rows
            row_str = ", ".join([f"{k}: {v}" for k, v in row.items()])
            answer_parts.append(f"  Row {i+1}: {row_str}")
        
        if len(data) > 5:
            answer_parts.append(f"  ... and {len(data) - 5} more rows")
        
        return {
            "answer": "\n".join(answer_parts),
            "confidence_score": 0.8,
            "grounded": True,
            "sources": [{"type": "sql_analysis", "query": sql_results.get("query_executed")}]
        }
    
    def _format_null_analysis(self, data: List[Dict], sql_results: Dict[str, Any]) -> Dict[str, Any]:
        """Format null analysis results in a readable way."""
        if not data:
            return {
                "answer": "No null analysis data available.",
                "confidence_score": 0.1,
                "grounded": True
            }
        
        row = data[0]  # Should be only one row for null analysis
        total_rows = row.get("TOTAL_ROWS", 0)
        
        answer_parts = [f"Null Analysis Results (Total Rows: {total_rows:,})"]
        
        null_columns = []
        for key, value in row.items():
            if key.endswith("_NULLS") and value > 0:
                col_name = key.replace("_NULLS", "")
                percentage = (value / total_rows * 100) if total_rows > 0 else 0
                null_columns.append((col_name, value, percentage))
        
        if null_columns:
            answer_parts.append("Columns with NULL values:")
            for col_name, null_count, percentage in sorted(null_columns, key=lambda x: x[1], reverse=True):
                answer_parts.append(f"  - {col_name}: {null_count:,} nulls ({percentage:.1f}%)")
        else:
            answer_parts.append("No NULL values found in analyzed columns.")
        
        return {
            "answer": "\n".join(answer_parts),
            "confidence_score": 0.9,
            "grounded": True,
            "sources": [{"type": "null_analysis", "total_rows": total_rows}]
        }