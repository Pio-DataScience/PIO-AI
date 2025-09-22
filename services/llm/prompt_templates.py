"""
Prompt templates for different types of queries.
"""

import sys
import os
from typing import Dict, List, Any
from dataclasses import dataclass

# Add package to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from services.retriever.router import QueryClassification


@dataclass
class PromptTemplate:
    """Template for constructing prompts."""
    system_prompt: str
    user_prompt: str
    context_prefix: str = ""
    context_suffix: str = ""


class PromptTemplates:
    """Collection of prompt templates for different query types."""
    
    @staticmethod
    def get_system_prompt(query_type: str) -> str:
        """Get base system prompt for query type."""
        base_context = """You are an expert programming assistant specialized in analyzing codebases and providing precise, helpful answers. You have access to code files, documentation, database schemas, and call graphs from the user's project.

Key capabilities:
- Code analysis and explanation
- Function/class/method lookups
- Database schema exploration and relationship analysis
- Join path finding and SQL generation
- Call graph traversal
- Documentation search
- Bug identification and fixes
- Implementation suggestions

Guidelines:
1. Be precise and reference specific files/line numbers when relevant
2. Provide code examples when helpful
3. For database queries, generate synthetic SQL but NEVER execute it
4. Explain complex concepts clearly
5. Suggest best practices
6. If information is incomplete, say so clearly
7. Use the provided context and citations
8. For schema queries, include table/column details and relationships
"""
        
        if query_type == "line_code":
            return base_context + """

SPECIALIZATION: You are analyzing a specific location in the code. Focus on:
- The exact symbol/function/class at that location
- Its relationships and dependencies
- How it's used in the broader codebase
- Potential issues or improvements
"""
        
        elif query_type == "code":
            return base_context + """

SPECIALIZATION: You are helping with general code understanding and development. Focus on:
- Finding relevant code patterns and implementations
- Explaining how different parts work together
- Suggesting improvements or alternatives
- Identifying potential bugs or issues
"""
        
        elif query_type == "schema":
            return base_context + """

SPECIALIZATION: You are analyzing database schemas and data structures. Focus on:
- Table relationships and constraints
- Column meanings and data types
- Query patterns and optimization
- Data modeling best practices
"""
        
        elif query_type == "schema_join":
            return base_context + """

SPECIALIZATION: You are analyzing database relationships and join paths. Focus on:
- Foreign key relationships between tables
- Join paths and how tables connect
- Generating SYNTHETIC SQL (never execute real queries)
- Cardinality and relationship quality
- Practical join patterns and best practices

CRITICAL: Never execute any SQL queries. Only provide synthetic examples for illustration.
"""
        
        elif query_type == "schema_explain":
            return base_context + """

SPECIALIZATION: You are explaining database schema elements and structure. Focus on:
- Detailed table and column descriptions
- Data types, constraints, and relationships
- Business context and usage patterns
- PII and sensitive data identification
- Schema design patterns and best practices
"""
        
        elif query_type == "doc":
            return base_context + """

SPECIALIZATION: You are helping with documentation and project understanding. Focus on:
- Configuration and setup instructions
- Usage examples and tutorials
- Architecture and design decisions
- Project organization and conventions
"""
        
        else:
            return base_context
    
    @staticmethod
    def get_user_prompt_template(query_type: str) -> str:
        """Get user prompt template for query type."""
        context_intro = "Based on the following context from the codebase:\n\n{context}\n\n"
        
        if query_type == "line_code":
            return context_intro + """The user is asking about line {line} in file {path}:

"{query}"

Please analyze the code at that location and provide a comprehensive answer. Include:
1. What the code does at that specific line
2. How it relates to the surrounding code
3. Any relevant patterns, relationships, or issues
4. Suggestions for improvement if applicable

Use the provided context and citations to give a complete picture."""
        
        elif query_type == "code":
            return context_intro + """The user is asking about code:

"{query}"

Please provide a comprehensive answer using the context. Include:
1. Direct answers to their question
2. Relevant code examples from the context
3. How different pieces fit together
4. Best practices or alternative approaches
5. Any potential issues to be aware of

Reference specific files and line numbers from the citations when relevant."""
        
        elif query_type == "schema":
            return context_intro + """The user is asking about database schema or data structures:

"{query}"

Please provide a comprehensive answer. Include:
1. Relevant table/column information
2. Relationships and constraints
3. How the schema is used in the code
4. Query patterns or examples
5. Suggestions for optimization or improvement

Use both the schema information and related code context."""
        
        elif query_type == "schema_join":
            return context_intro + """The user is asking about database table relationships and joins:

"{query}"

Please provide a comprehensive answer with:
1. The specific join path between tables (if found)
2. SYNTHETIC SQL example showing the join (clearly marked as example only)
3. Foreign key relationships and column mappings
4. Cardinality information (one-to-many, etc.)
5. Quality assessment of the relationships
6. Alternative join paths if available

IMPORTANT: All SQL is purely synthetic for illustration - never execute queries.
Include citations for all foreign key constraints and relationships mentioned."""

        elif query_type == "schema_explain":
            return context_intro + """The user is asking for explanation of database schema elements:

"{query}"

Please provide a detailed explanation including:
1. Table structure and purpose
2. Column details (types, constraints, meanings)
3. Relationships with other tables
4. PII or sensitive data indicators
5. Usage patterns and business context
6. Any constraints or business rules

Reference specific schema elements and include citations for table/column comments and metadata."""
        
        elif query_type == "doc":
            return context_intro + """The user is asking about documentation or project setup:

"{query}"

Please provide a comprehensive answer. Include:
1. Clear explanations of concepts or procedures
2. Step-by-step instructions if applicable
3. Configuration details and examples
4. References to relevant files and documentation
5. Troubleshooting tips if relevant

Focus on being practical and actionable."""
        
        else:
            return context_intro + """The user is asking:

"{query}"

Please provide a helpful and comprehensive answer using the provided context. Reference specific files, line numbers, and citations when relevant."""
    
    @staticmethod
    def create_prompt(query: str, context: str, classification: QueryClassification, 
                     project: str = "", path: str = "", line: int = 0) -> Dict[str, str]:
        """
        Create full prompt for the LLM.
        
        Args:
            query: User's question
            context: Assembled context from retrieval
            classification: Query classification
            project: Project name
            path: File path (for line queries)
            line: Line number (for line queries)
            
        Returns:
            Dict with 'system' and 'user' message content
        """
        system_prompt = PromptTemplates.get_system_prompt(classification.query_type)
        user_template = PromptTemplates.get_user_prompt_template(classification.query_type)
        
        # Format user prompt
        user_prompt = user_template.format(
            context=context,
            query=query,
            path=path,
            line=line,
            project=project
        )
        
        return {
            "system": system_prompt,
            "user": user_prompt
        }
    
    @staticmethod
    def create_messages(query: str, context: str, classification: QueryClassification,
                       project: str = "", path: str = "", line: int = 0) -> List[Dict[str, str]]:
        """
        Create message list for chat API.
        
        Returns:
            List of message dicts for chat API
        """
        prompt_dict = PromptTemplates.create_prompt(
            query, context, classification, project, path, line
        )
        
        return [
            {"role": "system", "content": prompt_dict["system"]},
            {"role": "user", "content": prompt_dict["user"]}
        ]
    
    @staticmethod
    def create_schema_join_prompt(query: str, join_result: Dict[str, Any]) -> List[Dict[str, str]]:
        """
        Create specialized prompt for schema join queries.
        
        Args:
            query: User's question
            join_result: Result from schema retriever find_join_path
            
        Returns:
            List of message dicts for chat API
        """
        system_prompt = PromptTemplates.get_system_prompt("schema_join")
        
        if join_result:
            context = f"""
JOIN PATH FOUND:
Source Table: {join_result['source_table']}
Target Table: {join_result['target_table']}
Path: {' → '.join(join_result['join_path'])}
Quality Score: {join_result['quality_score']}/1.0

SYNTHETIC SQL EXAMPLE:
{join_result['synthetic_sql']}

RELATIONSHIP DETAILS:
"""
            for i, rel in enumerate(join_result['relationships']):
                context += f"""
Relationship {i+1}:
- FK Table: {rel['fk_owner']}.{rel['fk_table']} ({rel['fk_constraint']})
- PK Table: {rel['pk_owner']}.{rel['pk_table']} ({rel['pk_constraint']})
- Cardinality: {rel['cardinality']}
- Quality: {rel['quality_score']}/1.0
- Column Mappings:"""
                for mapping in rel['column_mappings']:
                    context += f"""
  • {mapping['fk_column']} → {mapping['pk_column']} (position {mapping['position']})"""
                context += "\n"
            
            context += f"""
CITATIONS:
{chr(10).join(join_result['citations'])}
"""
        else:
            context = """
JOIN PATH: No direct relationship path found between the specified tables.

This could mean:
1. No foreign key relationships exist between these tables
2. The tables are not in the indexed catalog
3. Table names may not match exactly (check spelling/case)
4. Tables might be connected through intermediate tables beyond the search depth

Please verify table names and try searching for individual table schemas.
"""
        
        user_prompt = f"""The user is asking about a database table join:

"{query}"

Based on the join analysis above, please provide:
1. Clear explanation of the relationship (if found)
2. Analysis of the synthetic SQL example
3. Discussion of column mappings and their quality
4. Cardinality implications for query performance
5. Alternative approaches if the direct path isn't optimal

Remember: All SQL is synthetic for illustration only - never execute queries."""
        
        return [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ]
    
    @staticmethod 
    def create_schema_explain_prompt(query: str, table_info: Dict[str, Any]) -> List[Dict[str, str]]:
        """
        Create specialized prompt for schema explanation queries.
        
        Args:
            query: User's question
            table_info: Result from schema retriever explain_table
            
        Returns:
            List of message dicts for chat API
        """
        system_prompt = PromptTemplates.get_system_prompt("schema_explain")
        
        if 'error' in table_info:
            context = f"""
ERROR: {table_info['error']}

The requested table could not be found in the catalog. This might be because:
1. The table name is misspelled or has incorrect case
2. The table is not in the indexed schemas
3. The table exists but hasn't been harvested yet

Please check the table name and try searching with wildcards or partial names.
"""
        else:
            # Build detailed table context
            context = f"""
TABLE DETAILS:
Name: {table_info['table']}
Owner: {table_info['owner']}
Rows: {table_info.get('num_rows', 'Unknown')}
Last Analyzed: {table_info.get('last_analyzed', 'Unknown')}
Description: {table_info.get('comment', 'No description available')}

COLUMNS ({len(table_info.get('columns', []))} total):
"""
            
            # Group columns by type for better presentation
            for col in table_info.get('columns', []):
                pii_indicator = " [PII]" if col.get('is_pii') else ""
                nullable = "NULL" if col.get('nullable') == 'Y' else "NOT NULL"
                context += f"""
• {col['column_name']}: {col.get('data_type', 'Unknown')} {nullable}{pii_indicator}"""
            
            context += f"""

RELATIONSHIPS:
Incoming (referenced by other tables): {table_info.get('incoming_relationships', 0)}
Outgoing (references other tables): {table_info.get('outgoing_relationships', 0)}
"""
            
            # Add relationship details if available
            rel_details = table_info.get('relationship_details', {})
            if rel_details.get('incoming'):
                context += "\nTables that reference this table:\n"
                for rel in rel_details['incoming'][:5]:  # Limit to first 5
                    context += f"• {rel['fk_owner']}.{rel['fk_table']} via {rel['fk_constraint']}\n"
            
            if rel_details.get('outgoing'):
                context += "\nTables referenced by this table:\n"
                for rel in rel_details['outgoing'][:5]:  # Limit to first 5
                    context += f"• {rel['pk_owner']}.{rel['pk_table']} via {rel['pk_constraint']}\n"
        
        user_prompt = f"""The user is asking about a database table:

"{query}"

Based on the table information above, please provide:
1. Overview of the table's purpose and structure
2. Explanation of key columns and their meanings
3. Identification of any PII or sensitive data
4. Discussion of relationships with other tables
5. Any notable patterns or design considerations

Be thorough but focus on the most relevant aspects for the user's question."""
        
        return [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ]


# Convenience functions
def create_messages(query: str, context: str, classification: QueryClassification,
                   project: str = "", path: str = "", line: int = 0) -> List[Dict[str, str]]:
    """Create chat messages for the given query and context."""
    return PromptTemplates.create_messages(query, context, classification, project, path, line)


def create_prompt(query: str, context: str, classification: QueryClassification,
                 project: str = "", path: str = "", line: int = 0) -> Dict[str, str]:
    """Create prompt dict for the given query and context."""
    return PromptTemplates.create_prompt(query, context, classification, project, path, line)