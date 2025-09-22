#!/usr/bin/env python3
"""
Enhanced query processing for better keyword extraction.
"""

import re
from typing import List, Set


def extract_keywords_from_query(query: str) -> List[str]:
    """
    Extract relevant keywords from a natural language query.
    
    Args:
        query: Natural language query
        
    Returns:
        List of extracted keywords
    """
    # Convert to lowercase
    query = query.lower()
    
    # Remove common stop words
    stop_words = {
        'a', 'an', 'and', 'are', 'as', 'at', 'be', 'by', 'for', 'from',
        'has', 'he', 'in', 'is', 'it', 'its', 'of', 'on', 'that', 'the',
        'to', 'was', 'were', 'will', 'with', 'about', 'give', 'me', 'like',
        'tell', 'what', 'how', 'why', 'where', 'when', 'can', 'you', 'your',
        'this', 'that', 'these', 'those', 'i', 'my', 'we', 'our', 'they',
        'their', 'them', 'overview', 'explain', 'describe', 'show'
    }
    
    # Extract file names (with or without .py extension)
    file_patterns = re.findall(r'\b(\w+(?:_\w+)*(?:\.py)?)\b', query)
    
    # Extract technical terms and identifiers
    # Look for words with underscores, camelCase, or technical terms
    technical_terms = re.findall(r'\b(?:[A-Z]+|[a-z]+(?:_[a-z]+)+|[a-z]+[A-Z][a-z]*)\b', query)
    
    # Extract general words but filter stop words
    words = re.findall(r'\b[a-z]+\b', query)
    meaningful_words = [w for w in words if w not in stop_words and len(w) > 2]
    
    # Combine and deduplicate
    all_terms = set()
    
    # Add file-related terms (highest priority)
    for term in file_patterns:
        all_terms.add(term.replace('.py', ''))  # Add both with and without .py
        if '.py' in term:
            all_terms.add(term)
    
    # Add technical terms
    all_terms.update(technical_terms)
    
    # Add meaningful words (lower priority)
    all_terms.update(meaningful_words[:5])  # Limit to top 5 to avoid noise
    
    # Convert to list and prioritize, but filter out stop words again
    keywords = [term for term in all_terms if term.lower() not in stop_words]
    
    # Sort by likely relevance (file names first, then technical terms)
    def sort_key(term):
        if '_' in term or term.endswith('.py'):
            return 0  # Highest priority for file names
        elif any(c.isupper() for c in term):
            return 1  # Medium priority for technical terms
        else:
            return 2  # Lower priority for general words
    
    keywords.sort(key=sort_key)
    
    return keywords[:10]  # Return top 10 keywords


def enhance_query_with_keywords(original_query: str) -> str:
    """
    Create an enhanced query by extracting and combining keywords.
    
    Args:
        original_query: Original natural language query
        
    Returns:
        Enhanced query with extracted keywords using OR logic for better matching
    """
    keywords = extract_keywords_from_query(original_query)
    
    if not keywords:
        return original_query
    
    # Use OR logic to match any of the keywords instead of requiring all
    if len(keywords) == 1:
        return keywords[0]
    else:
        # Create OR query with top keywords for better BM25 matching
        top_keywords = keywords[:5]  # Use top 5 keywords
        return " OR ".join(top_keywords)


if __name__ == "__main__":
    # Test the keyword extraction
    test_queries = [
        "give me an overview about the AML outlier detection phases like the global_outlier.py file",
        "Tell me about the AI AML system",
        "what does the local_outlier.py file do in this system",
        "how do I use the clustering models",
        "explain the supervised_outlier detection algorithm"
    ]
    
    for query in test_queries:
        keywords = extract_keywords_from_query(query)
        enhanced = enhance_query_with_keywords(query)
        print(f"Original: {query}")
        print(f"Keywords: {keywords}")
        print(f"Enhanced: {enhanced}")
        print("---")