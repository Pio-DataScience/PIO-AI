"""
Hybrid retriever that orchestrates BM25, FAISS, and graph expansion.
"""

import sqlite3
import sys
import os
from pathlib import Path
from typing import List, Dict, Any, Optional, Set, Tuple
from dataclasses import dataclass

# Add package to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from services.retriever.router import QueryClassification, classify_query
from services.indexer.bm25_index import search_bm25
from services.indexer.faiss_index import search_faiss
from services.indexer.graph_index import callers_of, callees_of
from services.tools_api.ast_tools import where_is_line, get_symbols_in_file
from services.tools_api.schema_tools import search_schema, describe_table_safe
from services.ingest.manifest_reader import get_project_by_name
from services.retriever.query_enhancement import enhance_query_with_keywords


@dataclass
class SearchHit:
    """Unified search result from any source."""
    project: str
    path: str
    kind: str  # "code", "text", "symbol", "schema"
    source: str  # "bm25", "faiss", "graph", "ast", "schema"
    score: float
    content: str  # Snippet or description
    start_line: Optional[int] = None
    end_line: Optional[int] = None
    metadata: Optional[Dict[str, Any]] = None


class HybridRetriever:
    """Orchestrates multiple search strategies for comprehensive results."""
    
    def __init__(self):
        self.package_root = Path(__file__).resolve().parents[2]  # Fixed: was parents[3]
    
    def retrieve(self, query: str, project: str, path: str = "", line: int = 0, 
                max_results: int = 20) -> List[SearchHit]:
        """
        Main retrieval function that routes and combines results.
        
        Args:
            query: User's search query
            project: Project name
            path: Optional file path context
            line: Optional line number context
            max_results: Maximum results to return
            
        Returns:
            List of SearchHit objects, ranked and deduplicated
        """
        # Classify the query
        classification = classify_query(query, project, path, line)
        
        # Route to appropriate strategy
        if classification.query_type == "line_code":
            return self._retrieve_line_code(query, project, path, line, classification, max_results)
        elif classification.query_type == "code":
            return self._retrieve_code(query, project, classification, max_results)
        elif classification.query_type == "schema":
            return self._retrieve_schema(query, project, classification, max_results)
        elif classification.query_type == "doc":
            return self._retrieve_doc(query, project, classification, max_results)
        else:
            # Fallback to code search
            return self._retrieve_code(query, project, classification, max_results)
    
    def _retrieve_line_code(self, query: str, project: str, path: str, line: int,
                           classification: QueryClassification, max_results: int) -> List[SearchHit]:
        """Retrieve for line-specific code queries."""
        hits = []
        
        # 1. Get the specific symbol at the line
        if path and line:
            symbol_info = where_is_line(project, path, line)
            if symbol_info:
                hits.append(SearchHit(
                    project=project,
                    path=path,
                    kind="code",
                    source="ast",
                    score=1.0,
                    content=f"{symbol_info['kind']} {symbol_info['qualname']}",
                    start_line=symbol_info['start_line'],
                    end_line=symbol_info['end_line'],
                    metadata=symbol_info
                ))
                
                # 2. Get graph neighbors (±1 hop)
                graph_hits = self._expand_with_graph(project, symbol_info['qualname'])
                hits.extend(graph_hits)
        
        # 3. BM25 search for key terms from the symbol
        if hits:
            main_symbol = hits[0]
            qualname = main_symbol.metadata.get('qualname', '')
            if qualname:
                # Extract function/class name for BM25 search
                symbol_name = qualname.split('.')[-1]
                bm25_hits = self._search_bm25_code(project, symbol_name, max_results // 2)
                hits.extend(bm25_hits)
        
        return self._rank_and_dedupe(hits, max_results)
    
    def _retrieve_code(self, query: str, project: str, classification: QueryClassification,
                      max_results: int) -> List[SearchHit]:
        """Retrieve for general code queries."""
        hits = []
        
        # 1. BM25 search (primary)
        bm25_hits = self._search_bm25_code(project, query, max_results)
        hits.extend(bm25_hits)
        
        # 2. FAISS vector search (secondary)
        faiss_hits = self._search_faiss_code(project, query, max_results // 2)
        hits.extend(faiss_hits)
        
        # 3. Graph expansion for top BM25 results
        if classification.confidence > 0.7:
            top_symbols = self._extract_symbols_from_hits(hits[:3])
            for symbol in top_symbols:
                graph_hits = self._expand_with_graph(project, symbol)
                hits.extend(graph_hits)
        
        return self._rank_and_dedupe(hits, max_results)
    
    def _retrieve_schema(self, query: str, project: str, classification: QueryClassification,
                        max_results: int) -> List[SearchHit]:
        """Retrieve for schema/database queries."""
        hits = []
        
        # 1. Direct schema search (highest priority)
        schema_results = search_schema(query)
        for result in schema_results[:max_results // 2]:
            hits.append(SearchHit(
                project=project,
                path="<schema>",
                kind="schema",
                source="schema",
                score=0.9,
                content=f"{result['match_type']}: {result.get('table_name', '')}.{result.get('column_name', '')}",
                metadata=result
            ))
        
        # 2. Table descriptions for extracted table names
        schema_refs = classification.extracted_info.get('schema_references', [])
        for ref in schema_refs:
            if isinstance(ref, tuple) and len(ref) >= 1:
                table_name = ref[0]
                table_desc = describe_table_safe(table_name)
                if table_desc:
                    hits.append(SearchHit(
                        project=project,
                        path="<schema>",
                        kind="schema",
                        source="schema",
                        score=0.8,
                        content=f"Table {table_name}: {table_desc.get('table_comment', '')}",
                        metadata=table_desc
                    ))
        
        # 3. Fallback to BM25 search in code (for schema-related code)
        bm25_hits = self._search_bm25_code(project, query, max_results // 3)
        hits.extend(bm25_hits)
        
        return self._rank_and_dedupe(hits, max_results)
    
    def _retrieve_doc(self, query: str, project: str, classification: QueryClassification,
                     max_results: int) -> List[SearchHit]:
        """Retrieve for documentation queries."""
        hits = []
        
        # 1. BM25 search in text files (primary)
        bm25_hits = self._search_bm25_text(project, query, max_results)
        hits.extend(bm25_hits)
        
        # 2. FAISS vector search in text space
        faiss_hits = self._search_faiss_text(project, query, max_results // 2)
        hits.extend(faiss_hits)
        
        # 3. Also search code for configuration/setup related queries
        if any(term in query.lower() for term in ['config', 'setup', 'install', 'usage']):
            code_hits = self._search_bm25_code(project, query, max_results // 3)
            hits.extend(code_hits)
        
        return self._rank_and_dedupe(hits, max_results)
    
    def _search_bm25_code(self, project: str, query: str, max_results: int) -> List[SearchHit]:
        """Search BM25 index for code files."""
        try:
            # Enhance query with keyword extraction for better matching
            enhanced_query = enhance_query_with_keywords(query)
            results = search_bm25(project, enhanced_query, max_results * 2)  # Get extra to filter
            hits = []
            
            for result in results:
                if result.get('kind') == 'code':  # Only code files
                    hits.append(SearchHit(
                        project=result['project'],
                        path=result['path'],
                        kind="code",
                        source="bm25",
                        score=result['score'] * 0.8,  # Slight discount for BM25
                        content=result['snippet']
                    ))
                    
                    if len(hits) >= max_results:
                        break
            
            return hits
        except Exception as e:
            print(f"Warning: BM25 code search failed: {e}")
            import traceback
            traceback.print_exc()
            return []
    
    def _search_bm25_text(self, project: str, query: str, max_results: int) -> List[SearchHit]:
        """Search BM25 index for text files."""
        try:
            # Enhance query with keyword extraction for better matching
            enhanced_query = enhance_query_with_keywords(query)
            results = search_bm25(project, enhanced_query, max_results * 2)
            hits = []
            
            for result in results:
                if result.get('kind') == 'text':  # Only text files
                    hits.append(SearchHit(
                        project=result['project'],
                        path=result['path'],
                        kind="text",
                        source="bm25",
                        score=result['score'] * 0.8,
                        content=result['snippet']
                    ))
                    
                    if len(hits) >= max_results:
                        break
            
            return hits
        except Exception as e:
            print(f"Warning: BM25 text search failed: {e}")
            return []
    
    def _search_faiss_code(self, project: str, query: str, max_results: int) -> List[SearchHit]:
        """Search FAISS index for code space."""
        try:
            results = search_faiss(project, query, "code", max_results)
            hits = []
            
            for result in results:
                hits.append(SearchHit(
                    project=result['project'],
                    path=result['path'],
                    kind="code",
                    source="faiss",
                    score=result['score'] * 0.7,  # Discount for stub embeddings
                    content=result['preview'],
                    start_line=result['span'][0] if result.get('span') else None,
                    end_line=result['span'][1] if result.get('span') else None
                ))
            
            return hits
        except Exception as e:
            print(f"Warning: FAISS code search failed: {e}")
            return []
    
    def _search_faiss_text(self, project: str, query: str, max_results: int) -> List[SearchHit]:
        """Search FAISS index for text space."""
        try:
            results = search_faiss(project, query, "text", max_results)
            hits = []
            
            for result in results:
                hits.append(SearchHit(
                    project=result['project'],
                    path=result['path'],
                    kind="text",
                    source="faiss",
                    score=result['score'] * 0.7,
                    content=result['preview'],
                    start_line=result['span'][0] if result.get('span') else None,
                    end_line=result['span'][1] if result.get('span') else None
                ))
            
            return hits
        except Exception as e:
            print(f"Warning: FAISS text search failed: {e}")
            return []
    
    def _expand_with_graph(self, project: str, symbol_qualname: str) -> List[SearchHit]:
        """Expand results using call graph (±1 hop)."""
        hits = []
        
        try:
            # Get graph database path
            from services.tools_api.ast_tools import sanitize_project_name
            sanitized_name = sanitize_project_name(project)
            graph_db = self.package_root / "indexes" / "graph" / f"{sanitized_name}.sqlite"
            
            if not graph_db.exists():
                return hits
            
            con = sqlite3.connect(graph_db)
            
            # Get callees (functions this symbol calls)
            callees = callees_of(con, symbol_qualname)
            for callee in callees[:3]:  # Limit expansion
                hits.append(SearchHit(
                    project=project,
                    path=callee['file_path'],
                    kind="code",
                    source="graph",
                    score=0.6,
                    content=f"Called by {symbol_qualname}: {callee['callee_name']}",
                    start_line=callee.get('first_lineno'),
                    metadata={'relation': 'callee', 'caller': symbol_qualname}
                ))
            
            # Get callers (functions that call this symbol)
            callers = callers_of(con, symbol_qualname.split('.')[-1])  # Use simple name
            for caller in callers[:3]:
                hits.append(SearchHit(
                    project=project,
                    path=caller['file_path'],
                    kind="code",
                    source="graph",
                    score=0.6,
                    content=f"Calls {symbol_qualname}: {caller['caller_qual']}",
                    start_line=caller.get('first_lineno'),
                    metadata={'relation': 'caller', 'callee': symbol_qualname}
                ))
            
            con.close()
            
        except Exception as e:
            print(f"Warning: Graph expansion failed: {e}")
        
        return hits
    
    def _extract_symbols_from_hits(self, hits: List[SearchHit]) -> List[str]:
        """Extract symbol names from search hits for graph expansion."""
        symbols = []
        
        for hit in hits:
            # Look for function/class patterns in content
            import re
            
            # Extract from def/class patterns
            def_matches = re.findall(r'(?:def|class)\s+(\w+)', hit.content)
            symbols.extend(def_matches)
            
            # Extract from call patterns
            call_matches = re.findall(r'(\w+)\s*\(', hit.content)
            symbols.extend(call_matches)
            
            # Extract camelCase/snake_case identifiers
            identifier_matches = re.findall(r'\b[a-zA-Z_][a-zA-Z0-9_]*\b', hit.content)
            symbols.extend([m for m in identifier_matches if len(m) > 3])
        
        # Return unique symbols, limit to avoid explosion
        return list(set(symbols))[:5]
    
    def _rank_and_dedupe(self, hits: List[SearchHit], max_results: int) -> List[SearchHit]:
        """Rank and deduplicate search hits."""
        # Remove duplicates based on (path, content snippet)
        seen = set()
        unique_hits = []
        
        for hit in hits:
            key = (hit.path, hit.content[:100])  # Use first 100 chars as key
            if key not in seen:
                seen.add(key)
                unique_hits.append(hit)
        
        # Sort by score (descending)
        unique_hits.sort(key=lambda h: h.score, reverse=True)
        
        # Apply source-based boosting
        for hit in unique_hits:
            if hit.source == "ast":
                hit.score *= 1.2  # Boost AST results (most precise)
            elif hit.source == "schema":
                hit.score *= 1.1  # Boost schema results for schema queries
        
        # Re-sort after boosting
        unique_hits.sort(key=lambda h: h.score, reverse=True)
        
        return unique_hits[:max_results]


# Convenience functions
def retrieve(query: str, project: str, path: str = "", line: int = 0, 
            max_results: int = 20) -> List[SearchHit]:
    """Main retrieval function."""
    retriever = HybridRetriever()
    return retriever.retrieve(query, project, path, line, max_results)


def retrieve_with_classification(query: str, project: str, path: str = "", line: int = 0,
                               max_results: int = 20) -> Tuple[List[SearchHit], QueryClassification]:
    """Retrieve with query classification info."""
    classification = classify_query(query, project, path, line)
    retriever = HybridRetriever()
    hits = retriever.retrieve(query, project, path, line, max_results)
    return hits, classification
