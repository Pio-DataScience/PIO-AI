"""
Modern SQL Generator - LLM-powered with safety validation and optimization.
Production-ready with comprehensive error handling.
"""

import json
import re
from typing import Dict, List, Any, Optional
from datetime import datetime

from .observability import get_observability, log_performance

logger, tracer = get_observability()


class SQLGenerator:
    """
    Production SQL generator with safety, optimization, and self-healing capabilities.
    """
    
    def __init__(self, llm_provider):
        self.llm_provider = llm_provider
        
        # SQL templates for common operations
        self.templates = {
            "table_info": "SELECT * FROM {table_name} WHERE ROWNUM <= 5",
            "count_query": "SELECT COUNT(*) as total_records FROM {table_name}",
            "null_analysis": "SELECT COUNT(*) as null_count FROM {table_name} WHERE {column_name} IS NULL",
            "schema_query": "SELECT column_name, data_type, nullable FROM user_tab_columns WHERE table_name = '{table_name}'"
        }
        
        logger.log_operation(
            component="sql_generator",
            operation="initialize",
            phase="complete",
            outcome="success",
            templates_loaded=len(self.templates)
        )
    
    @log_performance("sql_generator", "generate_sql")
    async def generate_sql(self, 
                          query: str, 
                          intent: str,
                          schema_context: Dict[str, Any],
                          conversation_context: Dict[str, Any],
                          entities: Dict[str, List[str]]) -> Dict[str, Any]:
        """
        Generate safe SQL query based on natural language request.
        """
        
        try:
            # Try template-based generation first for common patterns
            template_sql = self._try_template_generation(query, intent, schema_context, entities)
            if template_sql:
                return {
                    "sql": template_sql,
                    "method": "template",
                    "confidence": 0.9,
                    "explanation": "Generated using optimized template"
                }
            
            # Use LLM for complex queries
            llm_sql = await self._llm_generate_sql(query, intent, schema_context, conversation_context, entities)
            return llm_sql
            
        except Exception as e:
            logger.log_error("sql_generator", "generate_sql", e)
            return {
                "sql": "",
                "method": "error",
                "confidence": 0.0,
                "error": str(e),
                "explanation": "SQL generation failed"
            }
    
    def _try_template_generation(self, 
                               query: str, 
                               intent: str,
                               schema_context: Dict[str, Any],
                               entities: Dict[str, List[str]]) -> Optional[str]:
        """Try to generate SQL using predefined templates."""
        
        query_lower = query.lower()
        tables = schema_context.get("tables", [])
        
        if not tables:
            return None
        
        # Handle both string table names and dict table objects
        primary_table = tables[0] if isinstance(tables[0], str) else tables[0].get("table_name", "")
        
        # Count queries
        if any(word in query_lower for word in ["how many", "count", "number of"]):
            if "null" in query_lower and entities.get("columns"):
                # Null count query
                column_name = entities["columns"][0].upper()
                return self.templates["null_analysis"].format(
                    table_name=primary_table,
                    column_name=column_name
                )
            else:
                # Total count
                return self.templates["count_query"].format(table_name=primary_table)
        
        # Schema exploration
        if any(word in query_lower for word in ["structure", "columns", "schema", "describe"]):
            return self.templates["schema_query"].format(table_name=primary_table)
        
        # Sample data
        if any(word in query_lower for word in ["show", "sample", "example", "data"]):
            return self.templates["table_info"].format(table_name=primary_table)
        
        return None
    
    async def _llm_generate_sql(self, 
                              query: str,
                              intent: str, 
                              schema_context: Dict[str, Any],
                              conversation_context: Dict[str, Any],
                              entities: Dict[str, List[str]]) -> Dict[str, Any]:
        """Generate SQL using LLM with comprehensive context."""
        
        # Build schema context for LLM
        schema_prompt = self._build_schema_prompt(schema_context)
        
        # Build conversation context
        context_prompt = ""
        if conversation_context.get("recent_entities"):
            context_prompt = f"\nRecent context: {conversation_context['recent_entities']}"
        
        sql_prompt = f"""You are an expert Oracle SQL developer for an AML (Anti-Money Laundering) database system.

TASK: Generate a safe, read-only SQL query for this request.

USER REQUEST: "{query}"
INTENT: {intent}

DATABASE SCHEMA:
{schema_prompt}

CONTEXT:
{context_prompt}

REQUIREMENTS:
1. Only SELECT statements (no INSERT, UPDATE, DELETE, DROP, etc.)
2. Use Oracle SQL syntax
3. Limit results with ROWNUM <= 100 for performance
4. Use proper table aliases
5. Include meaningful column aliases
6. Handle NULL values appropriately

EXAMPLE PATTERNS:
- Count query: SELECT COUNT(*) as record_count FROM table_name WHERE condition
- Sample data: SELECT * FROM table_name WHERE ROWNUM <= 10
- Null analysis: SELECT COUNT(*) as null_count FROM table WHERE column IS NULL

Generate ONLY the SQL query, no explanations:"""

        try:
            if self.llm_provider:
                # Use chat method with proper message format
                llm_response = self.llm_provider.chat(
                    messages=[{"role": "user", "content": sql_prompt}],
                    max_tokens=500,
                    temperature=0.1  # Low temperature for deterministic SQL
                )
                
                # Extract content from LLM response
                sql_response = llm_response.content if hasattr(llm_response, 'content') else str(llm_response)
                
                # Clean and validate the SQL
                clean_sql = self._clean_sql_response(sql_response)
                
                if clean_sql:
                    return {
                        "sql": clean_sql,
                        "method": "llm",
                        "confidence": 0.8,
                        "explanation": "Generated using LLM with schema context"
                    }
            
            # Fallback if LLM fails
            return self._generate_fallback_sql(schema_context, entities)
            
        except Exception as e:
            logger.log_error("sql_generator", "llm_generate_sql", e)
            return self._generate_fallback_sql(schema_context, entities)
    
    def _build_schema_prompt(self, schema_context: Dict[str, Any]) -> str:
        """Build comprehensive schema description for LLM."""
        
        tables = schema_context.get("tables", [])
        if not tables:
            return "No schema information available."
        
        schema_parts = []
        
        for table in tables[:3]:  # Limit to 3 tables for context window
            table_name = table["table_name"]
            table_desc = table.get("business_description", table.get("table_comment", ""))
            
            columns_info = []
            for col in table.get("columns", [])[:10]:  # Limit columns
                col_name = col["column_name"]
                col_type = col["data_type"]
                nullable = "NULL" if col.get("nullable") == "Y" else "NOT NULL"
                col_desc = col.get("business_description", col.get("column_comment", ""))
                
                columns_info.append(f"  {col_name} {col_type} {nullable} -- {col_desc}")
            
            table_part = f"""
TABLE: {table_name}
Description: {table_desc}
Columns:
{chr(10).join(columns_info)}
"""
            schema_parts.append(table_part)
        
        return "\n".join(schema_parts)
    
    def _clean_sql_response(self, sql_response: str) -> Optional[str]:
        """Clean and validate SQL response from LLM."""
        
        if not sql_response:
            return None
        
        # Extract SQL from response (remove markdown, explanations, etc.)
        sql_lines = []
        in_sql_block = False
        
        for line in sql_response.split('\n'):
            line = line.strip()
            
            # Skip empty lines and comments
            if not line or line.startswith('--'):
                continue
            
            # Detect SQL code blocks
            if line.startswith('```'):
                in_sql_block = not in_sql_block
                continue
            
            # Extract SQL content
            if in_sql_block or line.upper().startswith('SELECT'):
                sql_lines.append(line)
        
        if not sql_lines:
            # Try to extract any SELECT statement
            select_match = re.search(r'(SELECT\s+.*?(?:;|$))', sql_response, re.IGNORECASE | re.DOTALL)
            if select_match:
                return select_match.group(1).strip().rstrip(';')
            return None
        
        clean_sql = ' '.join(sql_lines).strip().rstrip(';')
        
        # Basic validation
        if not clean_sql.upper().startswith('SELECT'):
            return None
        
        # Remove dangerous keywords
        dangerous_keywords = ['INSERT', 'UPDATE', 'DELETE', 'DROP', 'CREATE', 'ALTER', 'TRUNCATE']
        sql_upper = clean_sql.upper()
        for keyword in dangerous_keywords:
            if keyword in sql_upper:
                return None
        
        return clean_sql
    
    def _generate_fallback_sql(self, schema_context: Dict[str, Any], entities: Dict[str, List[str]]) -> Dict[str, Any]:
        """Generate safe fallback SQL when LLM fails."""
        
        tables = schema_context.get("tables", [])
        if not tables:
            return {
                "sql": "",
                "method": "fallback",
                "confidence": 0.1,
                "error": "No schema available for fallback",
                "explanation": "Cannot generate SQL without schema"
            }
        
        # Handle both string table names and dict table objects
        primary_table = tables[0] if isinstance(tables[0], str) else tables[0].get("table_name", "")
        
        # Simple fallback: count query
        fallback_sql = f"SELECT COUNT(*) as record_count FROM {primary_table}"
        
        return {
            "sql": fallback_sql,
            "method": "fallback", 
            "confidence": 0.6,
            "explanation": f"Fallback count query for {primary_table}"
        }