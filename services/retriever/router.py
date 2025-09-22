"""
Query router for classifying and routing different types of queries.
"""

import re
import sys
import os
from typing import Literal, Dict, Any, List
from dataclasses import dataclass

# Add package to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))


@dataclass
class QueryClassification:
    """Query classification result."""
    query_type: Literal["line_code", "code", "schema", "schema_join", "schema_explain", "doc"]
    confidence: float
    reasoning: str
    extracted_info: Dict[str, Any]


class QueryRouter:
    """Routes queries to appropriate retrieval strategies."""
    
    def __init__(self):
        # Patterns for different query types
        self.line_code_patterns = [
            r'line\s+(\d+)',
            r':\s*(\d+)',
            r'@\s*line\s+(\d+)',
            r'at\s+line\s+(\d+)',
            r'(\w+\.py):(\d+)',
            r'(\w+\.sql):(\d+)',
        ]
        
        self.schema_patterns = [
            r'\b([A-Z_]{3,})\s*\.\s*([A-Z_]{3,})\b',  # TABLE.COLUMN
            r'\btable\s+([A-Z_]{3,})\b',
            r'\bcolumn\s+([A-Z_]{3,})\b',
            r'\bschema\b',
            r'\bddl\b',
            r'\bdatabase\b',
            r'\b([A-Z_]{4,})\s*(table|column|field)\b',
        ]
        
        # Enhanced patterns for join and relationship queries
        self.join_patterns = [
            r'\bjoin\s+(\w+)\s+(to|with|and)\s+(\w+)\b',
            r'\b(\w+)\s+(to|with|and)\s+(\w+)\s+relationship\b',
            r'\brelationship\s+between\s+(\w+)\s+and\s+(\w+)\b',
            r'\bhow\s+(to\s+)?connect\s+(\w+)\s+(to|with|and)\s+(\w+)\b',
            r'\blink\s+(\w+)\s+(to|with|and)\s+(\w+)\b',
            r'\bpath\s+from\s+(\w+)\s+to\s+(\w+)\b',
            r'\b(\w+)\s+related\s+to\s+(\w+)\b',
            r'\bforeign\s+key\s+from\s+(\w+)\s+to\s+(\w+)\b',
        ]
        
        # Enhanced schema inquiry patterns
        self.schema_inquiry_patterns = [
            r'\bwhere\s+is\s+(\w+)\b',
            r'\bfind\s+(\w+)\s+(table|column|field)\b',
            r'\bwhat\s+is\s+(\w+)\b',
            r'\bdescribe\s+(\w+)\b',
            r'\bexplain\s+(\w+)\b',
            r'\bshow\s+(\w+)\s+(structure|schema|columns)\b',
            r'\blist\s+(columns|fields)\s+(in|of|for)\s+(\w+)\b',
            r'\b(\w+)\s+(columns|fields|structure)\b',
        ]
        
        self.code_indicators = [
            'function', 'def ', 'class ', 'method', 'variable',
            'import', 'module', 'package', 'library',
            'api', 'endpoint', 'route', 'handler',
            'algorithm', 'implementation', 'logic',
            'bug', 'error', 'exception', 'debug',
            'test', 'unittest', 'pytest',
            'config', 'configuration', 'settings',
            'utils', 'utility', 'helper',
            'main', 'init', '__init__',
            'async', 'await', 'thread', 'process',
            'json', 'xml', 'yaml', 'csv',
            'sql', 'query', 'database', 'orm',
        ]
        
        self.doc_indicators = [
            'documentation', 'readme', 'guide', 'tutorial',
            'how to', 'example', 'usage', 'getting started',
            'installation', 'setup', 'configuration',
            'overview', 'introduction', 'explanation',
            'architecture', 'design', 'specification',
            'requirements', 'dependencies', 'changelog',
            'license', 'contributing', 'guidelines',
            'best practices', 'patterns', 'conventions',
            'faq', 'troubleshooting', 'help',
        ]
    
    def classify_query(self, query: str, project: str = "", 
                      path: str = "", line: int = 0) -> QueryClassification:
        """
        Classify a query to determine the best retrieval strategy.
        
        Args:
            query: The user's query
            project: Optional project context
            path: Optional file path context
            line: Optional line number context
            
        Returns:
            QueryClassification with routing information
        """
        query_lower = query.lower()
        extracted_info = {}
        
        # 1. Check for explicit line references (highest priority)
        if line > 0 or path:
            extracted_info.update({
                'path': path,
                'line': line,
                'project': project
            })
            return QueryClassification(
                query_type="line_code",
                confidence=0.95,
                reasoning="Explicit path and/or line number provided",
                extracted_info=extracted_info
            )
        
        # 2. Check for line patterns in query text
        for pattern in self.line_code_patterns:
            match = re.search(pattern, query, re.IGNORECASE)
            if match:
                extracted_info['line_reference'] = match.group(1) if match.groups() else match.group(0)
                if len(match.groups()) > 1:
                    extracted_info['file_reference'] = match.group(1)
                    extracted_info['line_reference'] = match.group(2)
                
                return QueryClassification(
                    query_type="line_code",
                    confidence=0.9,
                    reasoning=f"Line reference pattern found: {match.group(0)}",
                    extracted_info=extracted_info
                )
        
        # 3. Check for schema patterns with enhanced classification
        schema_score = 0
        schema_matches = []
        join_matches = []
        inquiry_matches = []
        
        # Check for join patterns (highest priority for schema queries)
        for pattern in self.join_patterns:
            matches = re.findall(pattern, query, re.IGNORECASE)
            if matches:
                schema_score += 0.5
                join_matches.extend(matches)
        
        # Check for schema inquiry patterns
        for pattern in self.schema_inquiry_patterns:
            matches = re.findall(pattern, query, re.IGNORECASE)
            if matches:
                schema_score += 0.4
                inquiry_matches.extend(matches)
        
        # Check for general schema patterns
        for pattern in self.schema_patterns:
            matches = re.findall(pattern, query, re.IGNORECASE)
            if matches:
                schema_score += 0.3
                schema_matches.extend(matches)
        
        # Populate extracted info for schema queries
        if schema_matches:
            extracted_info['schema_references'] = schema_matches
        if join_matches:
            extracted_info['join_references'] = join_matches
        if inquiry_matches:
            extracted_info['inquiry_references'] = inquiry_matches
        # Every thing of the above approches return 0 empty lists no match with basic querires
        # 4. Count code vs doc indicators
        code_score = 0
        doc_score = 0
        
        for indicator in self.code_indicators: # to general tend to hulucinate
            if indicator.lower() in query_lower:
                code_score += 0.1
        
        for indicator in self.doc_indicators:
            if indicator.lower() in query_lower:
                doc_score += 0.1
        
        # 5. Determine final classification with enhanced schema routing
        if schema_score > 0.5:
            # Determine specific schema query type
            if join_matches:
                return QueryClassification(
                    query_type="schema_join",
                    confidence=min(0.95, schema_score),
                    reasoning=f"Join/relationship patterns detected: {join_matches}",
                    extracted_info=extracted_info
                )
            elif inquiry_matches:
                return QueryClassification(
                    query_type="schema_explain",
                    confidence=min(0.9, schema_score),
                    reasoning=f"Schema inquiry patterns detected: {inquiry_matches}",
                    extracted_info=extracted_info
                )
            else:
                return QueryClassification(
                    query_type="schema",
                    confidence=min(0.8, schema_score),
                    reasoning=f"General schema patterns detected: {schema_matches}",
                    extracted_info=extracted_info
                )
        
        # Even with lower scores, check for strong join/inquiry indicators
        if join_matches:
            return QueryClassification(
                query_type="schema_join",
                confidence=0.7,
                reasoning=f"Join patterns detected: {join_matches}",
                extracted_info=extracted_info
            )
        
        if inquiry_matches:
            return QueryClassification(
                query_type="schema_explain",
                confidence=0.7,
                reasoning=f"Schema inquiry patterns detected: {inquiry_matches}",
                extracted_info=extracted_info
            )
        
        if code_score > doc_score and code_score > 0.2:
            return QueryClassification(
                query_type="code",
                confidence=min(0.8, code_score / (code_score + doc_score + 0.1)),
                reasoning=f"Code indicators detected (score: {code_score:.2f})",
                extracted_info=extracted_info
            )
        
        if doc_score > 0.1:
            return QueryClassification(
                query_type="doc",
                confidence=min(0.8, doc_score / (code_score + doc_score + 0.1)),
                reasoning=f"Documentation indicators detected (score: {doc_score:.2f})",
                extracted_info=extracted_info
            )
        
        # Default to code if unclear
        return QueryClassification(
            query_type="code",
            confidence=0.5,
            reasoning="Default classification - no strong indicators found",
            extracted_info=extracted_info
        )
    
    def extract_search_terms(self, query: str) -> List[str]:
        """
        Extract key search terms from a query.
        
        Args:
            query: User query
            
        Returns:
            List of important terms for searching
        """
        # Remove common stop words and query structure words
        stop_words = {
            'what', 'is', 'are', 'the', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at',
            'to', 'for', 'of', 'with', 'by', 'how', 'where', 'when', 'why', 'which',
            'this', 'that', 'these', 'those', 'i', 'you', 'he', 'she', 'it', 'we', 'they',
            'can', 'could', 'should', 'would', 'will', 'shall', 'may', 'might', 'must',
            'do', 'does', 'did', 'be', 'being', 'been', 'have', 'has', 'had',
            'explain', 'show', 'tell', 'find', 'search', 'look', 'see', 'get',
            'about', 'regarding', 'concerning', 'related', 'used', 'using', 'use'
        }
        
        # Extract words and filter
        words = re.findall(r'\b\w+\b', query.lower())
        terms = [w for w in words if w not in stop_words and len(w) > 2]
        
        # Also extract quoted phrases
        quoted_phrases = re.findall(r'"([^"]+)"', query) + re.findall(r"'([^']+)'", query)
        terms.extend(quoted_phrases)
        
        # Extract potential identifiers (CamelCase, snake_case, CONSTANTS)
        identifiers = re.findall(r'\b[A-Z][a-z]+(?:[A-Z][a-z]+)*\b', query)  # CamelCase
        identifiers += re.findall(r'\b[a-z]+(?:_[a-z]+)+\b', query)  # snake_case  
        identifiers += re.findall(r'\b[A-Z_]{3,}\b', query)  # CONSTANTS
        terms.extend(identifiers)
        
        # Remove duplicates while preserving order
        unique_terms = []
        seen = set()
        for term in terms:
            if term not in seen:
                unique_terms.append(term)
                seen.add(term)
        
        return unique_terms
    
    def should_use_graph_expansion(self, classification: QueryClassification) -> bool:
        """
        Determine if graph expansion should be used for this query.
        
        Args:
            classification: Query classification result
            
        Returns:
            True if graph expansion would be beneficial
        """
        # Use graph expansion for code queries and line-specific queries
        if classification.query_type in ("code", "line_code"):
            return True
        
        # Always use graph expansion for join queries
        if classification.query_type == "schema_join":
            return True
        
        # Also use for schema queries that might involve relationships
        if classification.query_type in ("schema", "schema_explain"):
            schema_refs = classification.extracted_info.get('schema_references', [])
            # Use graph expansion if we have table references (relationships might be relevant)
            return len(schema_refs) > 0
        
        return False
    
    def estimate_result_size(self, classification: QueryClassification, query: str) -> int:
        """
        Estimate how many results this query should return.
        
        Args:
            classification: Query classification result
            query: Original query
            
        Returns:
            Estimated number of results to retrieve
        """
        base_sizes = {
            "line_code": 3,       # Very specific, few results needed
            "code": 15,           # Moderate number for code searches
            "schema": 10,         # Schema queries usually need focused results
            "schema_join": 5,     # Join queries are very specific
            "schema_explain": 8,  # Explanation queries need moderate detail
            "doc": 20,            # Documentation might need more context
        }
        
        base_size = base_sizes[classification.query_type]
        
        # Adjust based on query specificity
        terms = self.extract_search_terms(query)
        
        if len(terms) == 1:
            # Single term - might be broad, get more results
            return base_size + 5
        elif len(terms) > 3:
            # Many terms - likely specific, fewer results needed
            return max(base_size - 3, 3)
        
        return base_size
    
    def extract_table_names(self, query: str) -> List[str]:
        """
        Extract potential table names from a query.
        
        Args:
            query: User query
            
        Returns:
            List of potential table names
        """
        tables = []
        
        # Look for uppercase identifiers (common table naming convention)
        uppercase_identifiers = re.findall(r'\b[A-Z][A-Z_]{2,}\b', query)
        tables.extend(uppercase_identifiers)
        
        # Look for OWNER.TABLE patterns
        owner_table_matches = re.findall(r'\b([A-Z_]{2,})\.([A-Z_]{2,})\b', query)
        for owner, table in owner_table_matches:
            tables.append(f"{owner}.{table}")
            tables.append(table)  # Also add just the table name
        
        # Look for table references after keywords
        table_keywords = ['table', 'from', 'join', 'into', 'update']
        for keyword in table_keywords:
            pattern = f'\\b{keyword}\\s+([A-Za-z_][A-Za-z0-9_]{{2,}})\\b'
            matches = re.findall(pattern, query, re.IGNORECASE)
            tables.extend([m.upper() for m in matches])
        
        # Remove duplicates while preserving order
        unique_tables = []
        seen = set()
        for table in tables:
            table_upper = table.upper()
            if table_upper not in seen:
                unique_tables.append(table_upper)
                seen.add(table_upper)
        
        return unique_tables
    
    def extract_join_intent(self, classification: QueryClassification) -> Dict[str, Any]:
        """
        Extract join intent details from a query classification.
        
        Args:
            classification: Query classification result
            
        Returns:
            Dictionary with join intent details
        """
        join_intent = {
            "is_join_query": classification.query_type == "schema_join",
            "table1": None,
            "table2": None,
            "join_type": "inner",  # default
            "bidirectional": True
        }
        
        if not join_intent["is_join_query"]:
            return join_intent
        
        join_refs = classification.extracted_info.get('join_references', [])
        
        if join_refs:
            # Extract tables from first join reference
            first_ref = join_refs[0]
            if isinstance(first_ref, tuple) and len(first_ref) >= 3:
                # Pattern like ('table1', 'to', 'table2')
                join_intent["table1"] = first_ref[0].upper()
                join_intent["table2"] = first_ref[2].upper() if len(first_ref) > 2 else first_ref[-1].upper()
            elif isinstance(first_ref, tuple) and len(first_ref) == 2:
                # Pattern like ('table1', 'table2')
                join_intent["table1"] = first_ref[0].upper()
                join_intent["table2"] = first_ref[1].upper()
        
        # If we couldn't extract from patterns, try to extract from all table names
        if not join_intent["table1"] or not join_intent["table2"]:
            table_names = self.extract_table_names(classification.extracted_info.get('original_query', ''))
            if len(table_names) >= 2:
                join_intent["table1"] = table_names[0]
                join_intent["table2"] = table_names[1]
        
        return join_intent


# Convenience functions
def classify_query(query: str, project: str = "", path: str = "", line: int = 0) -> QueryClassification:
    """Classify a query using the default router."""
    router = QueryRouter()
    return router.classify_query(query, project, path, line)


def extract_search_terms(query: str) -> List[str]:
    """Extract search terms from a query."""
    router = QueryRouter()
    return router.extract_search_terms(query)
