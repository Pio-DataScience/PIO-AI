"""
Modern Answer Composer - Natural language response generation with context awareness.
Production-ready with structured output and comprehensive error handling.
"""

import json
from typing import Dict, List, Any, Optional
from datetime import datetime

from .observability import get_observability, log_performance

logger, tracer = get_observability()


class AnswerComposer:
    """
    Production answer composer that generates natural, informative responses
    from SQL results with proper context integration.
    """
    
    def __init__(self, llm_provider):
        self.llm_provider = llm_provider
        
        # Response templates for common scenarios
        self.templates = {
            "count_result": "Found {count} records in {table_name}.",
            "null_analysis": "There are {null_count} null values in the {column_name} column of {table_name}.",
            "schema_info": "The {table_name} table has {column_count} columns: {columns}.",
            "sample_data": "Here are some sample records from {table_name}:",
            "no_results": "No records found matching your criteria in {table_name}.",
            "error": "I encountered an issue while retrieving data: {error_message}"
        }
        
        logger.log_operation(
            component="answer_composer",
            operation="initialize",
            phase="complete",
            outcome="success",
            templates_loaded=len(self.templates)
        )
    
    @log_performance("answer_composer", "compose_answer")
    async def compose_answer(self, 
                           query: str,
                           sql_query: str,
                           results: List[Dict[str, Any]],
                           schema_context: Dict[str, Any],
                           conversation_context: Dict[str, Any]) -> Dict[str, Any]:
        """
        Compose comprehensive natural language answer from SQL results.
        """
        
        try:
            # Debug input parameters
            print(f"DEBUG compose_answer: query='{query}'")
            print(f"DEBUG compose_answer: results type={type(results)}, length={len(results) if isinstance(results, list) else 'not a list'}")
            print(f"DEBUG compose_answer: schema_context type={type(schema_context)}")
            print(f"DEBUG compose_answer: conversation_context type={type(conversation_context)}")
            
            # Validate input types
            if not isinstance(results, list):
                print(f"ERROR: results is not a list, it's {type(results)}: {results}")
                results = []
            
            if not isinstance(schema_context, dict):
                print(f"ERROR: schema_context is not a dict, it's {type(schema_context)}: {schema_context}")
                schema_context = {}
                
            if not isinstance(conversation_context, dict):
                print(f"ERROR: conversation_context is not a dict, it's {type(conversation_context)}: {conversation_context}")
                conversation_context = {}
            
            # Determine response type based on query and results
            if not results:
                print("DEBUG: No results, calling _compose_no_results_response")
                return await self._compose_no_results_response(query, sql_query, schema_context)
            
            # Analyze query intent for appropriate response style
            print("DEBUG: Analyzing response type...")
            response_type = self._analyze_response_type(query, sql_query, results)
            print(f"DEBUG: Response type determined: {response_type}")
            
            if response_type == "count":
                print("DEBUG: Calling _compose_count_response")
                return await self._compose_count_response(query, results, schema_context)
            elif response_type == "schema":
                print("DEBUG: Calling _compose_schema_response")
                return await self._compose_schema_response(query, results, schema_context)
            elif response_type == "sample_data":
                print("DEBUG: Calling _compose_data_response")
                return await self._compose_data_response(query, results, schema_context)
            elif response_type == "analysis":
                print("DEBUG: Calling _compose_analysis_response")
                return await self._compose_analysis_response(query, results, schema_context, conversation_context)
            else:
                print("DEBUG: Calling _compose_general_response")
                return await self._compose_general_response(query, results, schema_context, conversation_context)
                
        except Exception as e:
            import traceback
            error_details = traceback.format_exc()
            print(f"ERROR in compose_answer: {e}")
            print(f"ERROR traceback: {error_details}")
            logger.log_error("answer_composer", "compose_answer", e, metadata={"traceback": error_details})
            return {
                "answer": "I found some data but had trouble formatting the response. Please try rephrasing your question.",
                "response_type": "error",
                "confidence": 0.3
            }
    
    def _analyze_response_type(self, query: str, sql_query: str, results: List[Dict[str, Any]]) -> str:
        """Analyze query and results to determine appropriate response type."""
        
        query_lower = query.lower()
        
        print(f"DEBUG: _analyze_response_type - query: {query_lower}")
        
        # Schema exploration (CHECK FIRST - most specific)
        if any(phrase in query_lower for phrase in ["tell me about", "describe", "what is", "table structure", "table details", "schema"]) or \
           any(word in query_lower for word in ["columns", "structure", "details"]):
            print("DEBUG: Detected SCHEMA query")
            return "schema"
        
        # Count queries (ONLY specific count requests)
        if any(phrase in query_lower for phrase in ["how many", "count of", "number of"]):
            print("DEBUG: Detected COUNT query")
            return "count"
        
        # Everything else is general - let LLM handle it
        print("DEBUG: Defaulting to GENERAL query - LLM will handle")
        return "general"
    
    async def _compose_count_response(self, query: str, results: List[Dict[str, Any]], schema_context: Dict[str, Any]) -> Dict[str, Any]:
        """Compose response for count queries."""
        
        if results and len(results) == 1:
            result = results[0]
            
            # Find count value (could be under different column names)
            count_value = None
            for key, value in result.items():
                if any(term in key.lower() for term in ["count", "total", "record"]):
                    count_value = value
                    break
            
            if count_value is not None:
                # Get table name from schema context
                table_name = "the table"
                if schema_context.get("tables"):
                    table_name = schema_context["tables"][0]["table_name"]
                
                # Format count with thousands separator
                formatted_count = f"{count_value:,}"
                
                if "null" in query.lower():
                    answer = f"I found {formatted_count} null values in {table_name}."
                else:
                    answer = f"There are {formatted_count} records in {table_name}."
                
                return {
                    "answer": answer,
                    "response_type": "count",
                    "confidence": 0.95,
                    "data_summary": {
                        "count": count_value,
                        "table": table_name
                    }
                }
        
        return {
            "answer": "I found a count result but couldn't interpret the value.",
            "response_type": "count",
            "confidence": 0.5
        }
    
    async def _compose_schema_response(self, query: str, results: List[Dict[str, Any]], schema_context: Dict[str, Any]) -> Dict[str, Any]:
        """Compose response for schema information queries using LLM with rich context."""
        print(f"DEBUG: _compose_schema_response called with {len(results)} results")
        
        # If results are empty, try to use vector_results from schema_context
        vector_results = schema_context.get("vector_results", [])
        if not results and vector_results:
            results = vector_results
        if not results:
            print("DEBUG: No results found, returning empty response")
            return {
                "answer": "No schema information found for the requested table.",
                "response_type": "schema", 
                "confidence": 0.3
            }

        # Extract and organize metadata for LLM context
        table_info = self._extract_table_metadata(results)
        print(f"DEBUG: Extracted metadata for table: {table_info['name']}")
        
        # Use LLM to generate natural response if available
        if self.llm_provider:
            try:
                llm_response = await self._llm_compose_schema(query, table_info)
                if llm_response:
                    return llm_response
            except Exception as e:
                print(f"DEBUG: LLM composition failed, using fallback: {e}")
        
        # Fallback to simple template response
        return self._fallback_schema_response(query, table_info)
    
    def _extract_table_metadata(self, results: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Extract structured metadata from vector search results with strict table filtering."""
        table_info = {
            "name": "the table",
            "total_columns": None,
            "aml_column_count": None,
            "purpose": "",
            "columns": []
        }
        
        # First, collect all table names from results
        table_names_in_results = set()
        for res in results:
            meta = res.get("metadata", {})
            tname = meta.get("table_name") or meta.get("TABLE_NAME")
            if tname and "PIO_" in tname:
                table_names_in_results.add(tname.strip())
        
        print(f"All tables found in results: {list(table_names_in_results)}")
        
        # Try to identify the PRIMARY table from the results based on frequency
        # The table with the most column results is likely the one being asked about
        table_column_counts = {}
        for res in results:
            meta = res.get("metadata", {})
            if meta.get("entity_type") == "column":
                tname = meta.get("table_name") or meta.get("TABLE_NAME")
                if tname:
                    tname = tname.strip()
                    table_column_counts[tname] = table_column_counts.get(tname, 0) + 1
        
        # Select the table with most columns in the results as the primary table
        primary_table_name = None
        if table_column_counts:
            primary_table_name = max(table_column_counts, key=table_column_counts.get)
            print(f"Primary table by column count: {primary_table_name} ({table_column_counts[primary_table_name]} columns)")
        elif table_names_in_results:
            # Fallback: use first table found
            primary_table_name = next(iter(table_names_in_results))
            print(f"Primary table by fallback: {primary_table_name}")
        
        if primary_table_name:
            table_info["name"] = primary_table_name
        
        # Second pass: collect data ONLY for the primary table
        columns_for_primary_table = []
        
        for res in results:
            meta = res.get("metadata", {})
            content = res.get("content", "")
            
            # Get table name for this result
            result_table_name = meta.get("table_name") or meta.get("TABLE_NAME")
            
            # STRICT FILTER: Only use results that match the primary table exactly
            if result_table_name and primary_table_name and result_table_name.strip() == primary_table_name.strip():
                
                # Look for table summary for this specific table
                if meta.get("entity_type") == "table_summary":
                    table_info["total_columns"] = meta.get("column_count")
                    table_info["aml_column_count"] = meta.get("aml_column_count", 0)
                    if "Business Purpose:" in content:
                        table_info["purpose"] = content.split("Business Purpose:")[-1].strip()
                
                # Collect column details ONLY for this specific table
                elif meta.get("entity_type") == "column":
                    col_name = meta.get("column_name") or meta.get("COLUMN_NAME")
                    data_type = meta.get("data_type") or meta.get("DATA_TYPE")
                    aml_required = meta.get("aml_required") or meta.get("AML_REQUIRED", "N")
                    
                    description = ""
                    if "Description:" in content:
                        desc_part = content.split("Description:")[1].split("\n")[0].strip()
                        description = desc_part
                    
                    if col_name and col_name != "<NA>":
                        columns_for_primary_table.append({
                            "name": col_name.strip(),
                            "type": data_type if data_type and data_type != "<NA>" else "Unknown",
                            "description": description,
                            "aml_required": aml_required == "Y",
                            "table_name": result_table_name  # Track source table for verification
                        })
                        print(f"Added column {col_name.strip()} from {result_table_name}")
            else:
                # Log filtered out results
                if result_table_name:
                    print(f"Filtered out column from {result_table_name} (not {primary_table_name})")
        
        table_info["columns"] = columns_for_primary_table
        
        print(f"Final metadata: Table={primary_table_name}, Columns={len(columns_for_primary_table)}")
        for col in columns_for_primary_table:
            print(f"   - {col['name']} ({col['type']})")
        
        return table_info
    
    async def _llm_compose_schema(self, query: str, table_info: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Use LLM to compose natural schema response with strict anti-hallucination measures."""
        
        # Build STRICT context summary from only actual retrieved data
        context_parts = [f"Table: {table_info['name']}"]
        
        if table_info["total_columns"]:
            context_parts.append(f"Total columns: {table_info['total_columns']}")
        if table_info["aml_column_count"] is not None:
            context_parts.append(f"AML required columns: {table_info['aml_column_count']}")
        if table_info["purpose"]:
            context_parts.append(f"Purpose: {table_info['purpose']}")
        
        # Add ONLY the actual retrieved columns (no inference)
        actual_columns = []
        if table_info["columns"]:
            context_parts.append(f"\nACTUAL COLUMNS FOUND IN DATABASE ({len(table_info['columns'])} columns):")
            for col in table_info["columns"]:
                col_info = f"- {col['name']}"
                if col.get('type') and col['type'] != 'Unknown':
                    col_info += f" ({col['type']})"
                if col.get('description'):
                    col_info += f": {col['description']}"
                if col.get('aml_required'):
                    col_info += " [AML required]"
                context_parts.append(col_info)
                actual_columns.append(col['name'])
        
        schema_context = "\n".join(context_parts)
        
        # Create STRICT anti-hallucination prompt
        # Create STRICT anti-hallucination prompt with accurate column count
        column_count_statement = ""
        if table_info["total_columns"]:
            column_count_statement = f"This table contains {table_info['total_columns']} columns in total"
            if table_info["aml_column_count"]:
                column_count_statement += f" (with {table_info['aml_column_count']} columns required for AML compliance)"
        elif len(table_info["columns"]) > 0:
            column_count_statement = f"Database shows at least {len(table_info['columns'])} columns (details shown below)"
        else:
            column_count_statement = "Column structure information is available"

        prompt = f"""You are a database analyst. Answer ONLY using the provided factual information below. DO NOT infer, assume, or make up any column names or details not explicitly listed.

USER QUESTION: "{query}"

FACTUAL TABLE INFORMATION FROM DATABASE:
{schema_context}

COLUMN COUNT ACCURACY: {column_count_statement}

STRICT INSTRUCTIONS:
1. Use ONLY the column names explicitly listed above - DO NOT mention any other columns
2. Use ONLY the data types and descriptions provided - DO NOT infer additional details  
3. If asked about columns not in the list, state "not found in available data"
4. Use natural language but stick strictly to the facts provided
5. Mention that this shows the columns found in the database dictionary
6. DO NOT use markdown, hashtags, or special formatting
7. Be accurate about the total column count - use the exact number provided: {table_info['total_columns'] if table_info['total_columns'] else 'information available'}

The columns listed above are the COMPLETE and ONLY columns you should reference.

Answer:"""

        try:
            llm_response = self.llm_provider.chat(
                messages=[{"role": "user", "content": prompt}],
                max_tokens=800,  # Reduced to prevent elaboration
                temperature=0.1  # Very low temperature to prevent creativity
            )
            
            if llm_response and llm_response.content and len(llm_response.content.strip()) > 20:
                response_text = llm_response.content.strip()
                
                # Additional hallucination check: ensure no unknown columns are mentioned
                mentioned_columns = []
                for word in response_text.split():
                    # Clean word of punctuation
                    clean_word = word.strip('.,:-()[]{}').upper()
                    if '_' in clean_word and any(clean_word.startswith(prefix) for prefix in ['PIO_', 'BI_', 'DWH_', 'ACT_', 'BOND_', 'CUS_', 'DEAL_']):
                        mentioned_columns.append(clean_word)
                
                # Check if mentioned columns are in actual retrieved columns
                invalid_mentions = []
                actual_columns_upper = [col.upper() for col in actual_columns]
                for mentioned in mentioned_columns:
                    if mentioned not in actual_columns_upper and mentioned != table_info['name'].upper():
                        invalid_mentions.append(mentioned)
                
                if invalid_mentions:
                    print(f"HALLUCINATION DETECTED: LLM mentioned non-existent columns: {invalid_mentions}")
                    print(f"Actual columns in database: {actual_columns}")
                    # Fall back to template response to avoid hallucination
                    return self._fallback_schema_response(query, table_info)
                
                return {
                    "answer": response_text,
                    "response_type": "schema",
                    "confidence": 0.9,
                    "method": "llm_generated_verified",
                    "data_summary": {
                        "table": table_info["name"],
                        "total_columns": table_info["total_columns"],
                        "detailed_columns": len(table_info["columns"]),
                        "aml_columns": table_info["aml_column_count"],
                        "verified_columns": actual_columns
                    }
                }
        except Exception as e:
            print(f"DEBUG: LLM generation failed: {e}")
        
        return None
    
    def _fallback_schema_response(self, query: str, table_info: Dict[str, Any]) -> Dict[str, Any]:
        """Fallback template-based response using ONLY factual data - no hallucination."""
        
        answer_parts = []
        
        # Table name and basic info
        table_name = table_info['name']
        answer_parts.append(f"The {table_name} table")
        
        # Column count information
        if table_info["total_columns"]:
            answer_parts.append(f"contains {table_info['total_columns']} columns")
            if table_info["aml_column_count"] is not None:
                answer_parts.append(f"({table_info['aml_column_count']} are required for AML compliance)")
        
        # Purpose if available
        if table_info["purpose"]:
            answer_parts.append(f"and serves the business purpose: {table_info['purpose']}")
        
        # List ONLY the actual columns found in the database
        if table_info["columns"]:
            column_names = [col['name'] for col in table_info["columns"]]
            answer_parts.append(f"\n\nActual columns found in database ({len(column_names)} columns):")
            
            # Show columns with their data types
            column_details = []
            for col in table_info["columns"]:
                col_detail = col['name']
                if col.get('type') and col['type'] != 'Unknown':
                    col_detail += f" ({col['type']})"
                column_details.append(col_detail)
            
            # Group columns for better readability
            if len(column_details) <= 10:
                answer_parts.append(", ".join(column_details))
            else:
                # Show first 10 and mention there are more
                answer_parts.append(", ".join(column_details[:10]) + f", and {len(column_details) - 10} more columns")
        else:
            answer_parts.append("(column details not available in current query results)")
        
        answer = " ".join(answer_parts) + "."
        
        # Clean up any double spaces
        answer = " ".join(answer.split())
        
        return {
            "answer": answer,
            "response_type": "schema",
            "confidence": 0.8,  # High confidence since it's factual only
            "method": "template_factual_only",
            "data_summary": {
                "table": table_info["name"],
                "total_columns": table_info["total_columns"],
                "detailed_columns": len(table_info["columns"]),
                "aml_columns": table_info["aml_column_count"],
                "factual_only": True  # Flag to indicate no hallucination risk
            }
        }
    
    async def _compose_data_response(self, query: str, results: List[Dict[str, Any]], schema_context: Dict[str, Any]) -> Dict[str, Any]:
        """Compose response for sample data queries."""
        
        if not results:
            return await self._compose_no_results_response(query, "", schema_context)
        
        # Get table information
        table_name = "the table"
        if schema_context.get("tables"):
            table_name = schema_context["tables"][0]["table_name"]
        
        # Format results for display
        answer_parts = [f"Here are {len(results)} sample records from {table_name}:"]
        
        # Show first few records in a readable format
        for i, record in enumerate(results[:5]):  # Limit to 5 records for readability
            record_parts = []
            for key, value in record.items():
                if value is not None:
                    # Truncate long values
                    str_value = str(value)
                    if len(str_value) > 50:
                        str_value = str_value[:47] + "..."
                    record_parts.append(f"{key}: {str_value}")
                else:
                    record_parts.append(f"{key}: NULL")
            
            answer_parts.append(f"\nRecord {i+1}: {', '.join(record_parts[:5])}")  # Limit columns shown
        
        if len(results) > 5:
            answer_parts.append(f"\n... and {len(results) - 5} more records.")
        
        return {
            "answer": "\n".join(answer_parts),
            "response_type": "sample_data",
            "confidence": 0.85,
            "data_summary": {
                "table": table_name,
                "records_shown": min(5, len(results)),
                "total_records": len(results),
                "columns": list(results[0].keys()) if results else []
            }
        }
    
    async def _compose_analysis_response(self, query: str, results: List[Dict[str, Any]], schema_context: Dict[str, Any], conversation_context: Dict[str, Any]) -> Dict[str, Any]:
        """Compose response for analytical queries."""
        
        # Use LLM for complex analysis if available
        if self.llm_provider and len(results) > 0:
            return await self._llm_compose_analysis(query, results, schema_context, conversation_context)
        
        # Fallback to template-based response
        return await self._compose_general_response(query, results, schema_context, conversation_context)
    
    async def _llm_compose_analysis(self, query: str, results: List[Dict[str, Any]], schema_context: Dict[str, Any], conversation_context: Dict[str, Any]) -> Dict[str, Any]:
        """Use LLM to compose analytical response."""
        
        try:
            # Prepare context for LLM
            results_summary = self._summarize_results_for_llm(results)
            schema_summary = self._summarize_schema_for_llm(schema_context)
            
            analysis_prompt = f"""You are an AML database analyst. Provide a clear, informative response to the user's question based on the SQL query results.

USER QUESTION: "{query}"

QUERY RESULTS SUMMARY:
{results_summary}

TABLE SCHEMA:
{schema_summary}

INSTRUCTIONS:
1. Directly answer the user's question
2. Highlight key findings and patterns
3. Use business-friendly language (avoid technical jargon)
4. Keep response concise but informative
5. If analyzing null values, explain potential data quality implications

Provide a natural, helpful response:"""

            llm_response = self.llm_provider.generate_response(
                query=analysis_prompt,
                context="",
                max_tokens=400,
                temperature=0.3
            )
            
            if llm_response and len(llm_response.strip()) > 20:
                return {
                    "answer": llm_response.strip(),
                    "response_type": "analysis",
                    "confidence": 0.8,
                    "method": "llm_composed"
                }
                
        except Exception as e:
            logger.log_error("answer_composer", "llm_compose_analysis", e)
        
        # Fallback if LLM fails
        return await self._compose_general_response(query, results, schema_context, conversation_context)
    
    async def _compose_general_response(self, query: str, results: List[Dict[str, Any]], schema_context: Dict[str, Any], conversation_context: Dict[str, Any]) -> Dict[str, Any]:
        """Compose general response using LLM with context awareness."""
        
        try:
            print(f"DEBUG _compose_general_response: results type={type(results)}, length={len(results) if isinstance(results, list) else 'not a list'}")
            print(f"DEBUG _compose_general_response: schema_context type={type(schema_context)}")
            print(f"DEBUG _compose_general_response: conversation_context type={type(conversation_context)}")
            
            # Check if we should use conversation context first (memory-aware responses)
            previous_table_context = conversation_context.get("current_table_context")
            if previous_table_context and not results:
                print("DEBUG: Using previous table context from conversation memory")
                return await self._llm_compose_from_memory(query, previous_table_context, conversation_context)
            
            if not results:
                print("DEBUG: No results in _compose_general_response, calling _compose_no_results_response")
                return await self._compose_no_results_response(query, "", schema_context)
            
            # Validate results is actually a list of dicts
            if not isinstance(results, list):
                print(f"ERROR: results is not a list in _compose_general_response: {type(results)}")
                return {
                    "answer": "I encountered an issue processing the results. Please try rephrasing your question.",
                    "response_type": "error",
                    "confidence": 0.3
                }
            
            # Check if schema_context is valid
            if not isinstance(schema_context, dict):
                print(f"ERROR: schema_context is not a dict in _compose_general_response: {type(schema_context)}")
                schema_context = {}
            
            # Use LLM to compose natural response with full context
            if self.llm_provider:
                print("DEBUG: Using LLM to compose general response")
                return await self._llm_compose_general(query, results, schema_context, conversation_context)
            
            # Fallback to template response if no LLM
            print("DEBUG: No LLM available, using template fallback")
            return self._template_general_response(query, results, schema_context)
            
        except Exception as e:
            import traceback
            error_details = traceback.format_exc()
            print(f"ERROR in _compose_general_response: {e}")
            print(f"ERROR traceback: {error_details}")
            return {
                "answer": "I encountered an issue formatting the response. Please try rephrasing your question.",
                "response_type": "error",
                "confidence": 0.3
            }
    
    async def _compose_no_results_response(self, query: str, sql_query: str, schema_context: Dict[str, Any]) -> Dict[str, Any]:
        """Compose response when no results are found."""
        
        table_name = "the table"
        if schema_context.get("tables"):
            table_name = schema_context["tables"][0]["table_name"]
        
        answer = f"No records were found in {table_name} matching your criteria."
        
        # Add helpful suggestions
        if "null" in query.lower():
            answer += " This could mean there are no null values in the specified column, which is good for data quality."
        else:
            answer += " You might want to try a broader search or check if the table contains the type of data you're looking for."
        
            return {
                "answer": answer,
                "response_type": "no_results",
                "confidence": 0.8
            }
    
    async def _llm_compose_from_memory(self, query: str, table_context: Dict[str, Any], conversation_context: Dict[str, Any]) -> Dict[str, Any]:
        """Use conversation memory to answer questions about previously discussed tables."""
        
        print("DEBUG: Composing response from conversation memory")
        
        try:
            # Extract table information from memory
            table_name = table_context.get("table_name", "the table")
            columns_info = table_context.get("columns", [])
            table_purpose = table_context.get("purpose", "")
            
            # Build context from memory
            context_parts = [f"Table: {table_name}"]
            if table_purpose:
                context_parts.append(f"Purpose: {table_purpose}")
            
            if columns_info:
                context_parts.append(f"\nAvailable columns:")
                for col in columns_info[:15]:  # Show more columns from memory
                    col_name = col.get("name", "Unknown")
                    col_type = col.get("type", "Unknown")
                    col_desc = col.get("description", "No description")
                    aml_status = "AML required" if col.get("aml_required") else "Optional"
                    context_parts.append(f"- {col_name} ({col_type}): {col_desc} [{aml_status}]")
            
            memory_context = "\n".join(context_parts)
            
            # Create LLM prompt using memory
            prompt = f"""You are an AML database analyst. The user is asking about a table we've already discussed. Use the existing context to answer their question naturally.

USER QUESTION: "{query}"

EXISTING TABLE CONTEXT FROM CONVERSATION:
{memory_context}

INSTRUCTIONS:
1. Answer the user's question directly using the table information we already have
2. Focus on the specific column or aspect they're asking about
3. Use natural, conversational language (no markdown, hashtags, or emojis)
4. If the specific column they mention exists in our context, describe its purpose and details
5. If the column doesn't exist in our context, let them know it wasn't found in this table
6. Keep the response helpful and business-focused

Answer:"""

            llm_response = self.llm_provider.chat(
                messages=[{"role": "user", "content": prompt}],
                max_tokens=800,
                temperature=0.6
            )
            
            if llm_response and llm_response.content and len(llm_response.content.strip()) > 20:
                return {
                    "answer": llm_response.content.strip(),
                    "response_type": "memory_based",
                    "confidence": 0.9,
                    "method": "conversation_memory",
                    "data_summary": {
                        "table": table_name,
                        "source": "conversation_memory",
                        "columns_available": len(columns_info)
                    }
                }
                
        except Exception as e:
            print(f"DEBUG: Memory-based LLM composition failed: {e}")
        
        # Fallback if memory approach fails
        return {
            "answer": f"I remember we were discussing {table_context.get('table_name', 'a table')}, but I need to search for more specific information about your question.",
            "response_type": "memory_fallback",
            "confidence": 0.5
        }
    
    async def _llm_compose_general(self, query: str, results: List[Dict[str, Any]], schema_context: Dict[str, Any], conversation_context: Dict[str, Any]) -> Dict[str, Any]:
        """Use LLM to compose general response with full context awareness."""
        
        try:
            # Validate if query asks about specific column that doesn't exist in results
            requested_column = self._extract_column_from_query(query)
            if requested_column:
                column_found = self._validate_column_in_results(requested_column, results)
                if not column_found:
                    print(f"WARNING: User asked about column '{requested_column}' but it was not found in vector search results")
                    return {
                        "answer": f"I couldn't find information about the column '{requested_column}' in the search results. This column may not exist in the database or might have a different name. Could you double-check the column name or ask me to search for similar columns?",
                        "response_type": "column_not_found",
                        "confidence": 0.8,
                        "method": "validation_check"
                    }
            
            # Prepare rich context for LLM
            results_context = self._prepare_results_context(results)
            schema_summary = self._extract_schema_summary(schema_context)
            conversation_summary = conversation_context.get("summary", "")
            
            # Build comprehensive prompt with validation instructions
            prompt = f"""You are an AML database analyst. Answer the user's question using ONLY the available data and context provided below.

USER QUESTION: "{query}"

DATA RESULTS:
{results_context}

SCHEMA CONTEXT:
{schema_summary}

CONVERSATION CONTEXT:
{conversation_summary}

CRITICAL INSTRUCTIONS:
1. ONLY use information that is explicitly provided in the DATA RESULTS above
2. If asking about a specific column, ONLY describe it if it appears in the results
3. DO NOT make up or infer column details that are not in the provided data
4. If the specific column they ask about is not in the results, clearly state that
5. Use natural, professional language (no markdown, hashtags, or emojis)
6. Be conversational and helpful but accurate
7. If the data doesn't contain what they're looking for, suggest checking the column name

Answer:"""

            llm_response = self.llm_provider.chat(
                messages=[{"role": "user", "content": prompt}],
                max_tokens=1000,
                temperature=0.6
            )
            
            if llm_response and llm_response.content and len(llm_response.content.strip()) > 20:
                return {
                    "answer": llm_response.content.strip(),
                    "response_type": "general",
                    "confidence": 0.9,
                    "method": "llm_generated",
                    "data_summary": {
                        "total_results": len(results),
                        "has_schema": bool(schema_context.get("tables")),
                        "has_conversation": bool(conversation_summary)
                    }
                }
                
        except Exception as e:
            print(f"DEBUG: LLM general composition failed: {e}")
        
        # Fallback to template
        return self._template_general_response(query, results, schema_context)
    
    def _prepare_results_context(self, results: List[Dict[str, Any]]) -> str:
        """Prepare results context for LLM consumption."""
        
        if not results:
            return "No data results available."
        
        context_parts = [f"Found {len(results)} results:"]
        
        # For vector search results (metadata format)
        if results and "metadata" in results[0]:
            context_parts.append("\nColumn Information:")
            for i, result in enumerate(results[:10]):  # Limit to 10 results
                meta = result.get("metadata", {})
                content = result.get("content", "")
                
                col_name = meta.get("column_name", "Unknown")
                table_name = meta.get("table_name", "Unknown")
                data_type = meta.get("data_type", "Unknown")
                
                # Extract description from content
                description = "No description"
                if "Description:" in content:
                    desc_part = content.split("Description:")[1].split("\n")[0].strip()
                    if desc_part:
                        description = desc_part
                
                context_parts.append(f"- {col_name} in {table_name} ({data_type}): {description}")
        
        # For regular SQL results
        else:
            sample_data = []
            for i, record in enumerate(results[:3]):
                if isinstance(record, dict):
                    record_summary = []
                    for key, value in record.items():
                        if isinstance(value, (int, float)):
                            record_summary.append(f"{key}: {value}")
                        elif value is None:
                            record_summary.append(f"{key}: NULL")
                        else:
                            str_value = str(value)[:40]
                            record_summary.append(f"{key}: {str_value}")
                    sample_data.append(f"Record {i+1}: {', '.join(record_summary)}")
            
            if sample_data:
                context_parts.extend(sample_data)
        
        return "\n".join(context_parts)
    
    def _extract_schema_summary(self, schema_context: Dict[str, Any]) -> str:
        """Extract schema summary for LLM context."""
        
        if not schema_context:
            return "No schema context available."
        
        summary_parts = []
        
        # Table information
        tables = schema_context.get("tables", [])
        if tables:
            if isinstance(tables[0], str):
                summary_parts.append(f"Table: {tables[0]}")
            elif isinstance(tables[0], dict):
                table_name = tables[0].get("table_name", "Unknown")
                summary_parts.append(f"Table: {table_name}")
        
        # Vector results summary
        vector_results = schema_context.get("vector_results", [])
        if vector_results:
            summary_parts.append(f"Vector search returned {len(vector_results)} related items")
        
        return "\n".join(summary_parts) if summary_parts else "No schema information available."
    
    def _template_general_response(self, query: str, results: List[Dict[str, Any]], schema_context: Dict[str, Any]) -> Dict[str, Any]:
        """Template-based fallback response when LLM is not available."""
        
        # Get table name safely
        table_name = "the requested data"
        tables = schema_context.get("tables", [])
        if tables and isinstance(tables, list) and len(tables) > 0:
            if isinstance(tables[0], dict) and "table_name" in tables[0]:
                table_name = tables[0]["table_name"]
            elif isinstance(tables[0], str):
                table_name = tables[0]
        
        # Provide a general informative response
        if len(results) == 1:
            answer = f"I found 1 record in {table_name} matching your query."
        else:
            answer = f"I found {len(results)} records in {table_name} matching your query."
        
        # Add some detail about the data safely
        if results and isinstance(results[0], dict):
            column_count = len(results[0].keys())
            answer += f" The results contain {column_count} columns of information."
            columns = list(results[0].keys())
        else:
            columns = []
        
        return {
            "answer": answer,
            "response_type": "general",
            "confidence": 0.7,
            "method": "template_fallback",
            "data_summary": {
                "table": table_name,
                "record_count": len(results),
                "columns": columns
            }
            }
    
    def _summarize_results_for_llm(self, results: List[Dict[str, Any]]) -> str:
        """Create a concise summary of results for LLM context."""
        
        if not results:
            return "No results returned."
        
        summary_parts = [f"Total records: {len(results)}"]
        
        # Show structure of first few records
        for i, record in enumerate(results[:3]):
            record_summary = []
            for key, value in record.items():
                if isinstance(value, (int, float)):
                    record_summary.append(f"{key}: {value}")
                elif value is None:
                    record_summary.append(f"{key}: NULL")
                else:
                    str_value = str(value)[:30]  # Truncate for context
                    record_summary.append(f"{key}: {str_value}")
            
            summary_parts.append(f"Record {i+1}: {', '.join(record_summary)}")
        
        if len(results) > 3:
            summary_parts.append(f"... and {len(results) - 3} more records")
        
        return "\n".join(summary_parts)
    
    def _summarize_schema_for_llm(self, schema_context: Dict[str, Any]) -> str:
        """Create schema summary for LLM context."""
        
        tables = schema_context.get("tables", [])
        if not tables:
            return "No schema information available."
        
        table = tables[0]  # Focus on primary table
        table_name = table["table_name"]
        table_desc = table.get("business_description", "")
        
        columns = table.get("columns", [])
        key_columns = [col["column_name"] for col in columns[:5]]  # First 5 columns
        
        summary = f"Table: {table_name}"
        if table_desc:
            summary += f" - {table_desc}"
        summary += f"\nKey columns: {', '.join(key_columns)}"
        
        return summary
    
    def _extract_column_from_query(self, query: str) -> Optional[str]:
        """Extract column name that user is asking about from their query."""
        
        import re
        
        # Common patterns for column questions
        patterns = [
            r"column\s+named\s+([A-Z_][A-Z0-9_]*)",  # "column named NEW_OPENED_ACC"
            r"column\s+([A-Z_][A-Z0-9_]*)",          # "column NEW_OPENED_ACC"
            r"([A-Z_][A-Z0-9_]*)\s+column",          # "NEW_OPENED_ACC column"
            r"about\s+([A-Z_][A-Z0-9_]*)",           # "about NEW_OPENED_ACC"
        ]
        
        query_upper = query.upper()
        
        for pattern in patterns:
            match = re.search(pattern, query_upper)
            if match:
                column_name = match.group(1)
                # Filter out common words that might match
                if column_name not in ['TABLE', 'DATABASE', 'SCHEMA', 'DATA', 'COLUMN', 'FIELD']:
                    return column_name
        
        return None
    
    def _validate_column_in_results(self, column_name: str, results: List[Dict[str, Any]]) -> bool:
        """Check if the specified column appears in the vector search results."""
        
        if not results or not column_name:
            return False
        
        column_name_upper = column_name.upper()
        
        for result in results:
            # Check metadata
            meta = result.get("metadata", {})
            result_column = meta.get("column_name", "")
            
            if result_column.upper() == column_name_upper:
                return True
            
            # Also check content for mentions
            content = result.get("content", "")
            if f"Column: {column_name}" in content or f"COLUMN: {column_name}" in content:
                return True
        
        return False