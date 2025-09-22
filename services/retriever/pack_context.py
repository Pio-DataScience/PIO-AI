"""
Context packing module for assembling final context with excerpts and citations.
"""

import sys
import os
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass

# Add package to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from services.retriever.hybrid import SearchHit
from services.tools_api.fs_tools import read_file
from services.ingest.manifest_reader import get_project_by_name


@dataclass
class ContextExcerpt:
    """A code/text excerpt with metadata."""
    project: str
    path: str
    content: str
    start_line: int
    end_line: int
    hit_source: str  # Which search found this
    hit_score: float
    expansion_context: bool = False  # Was this expanded from a hit?


@dataclass
class PackedContext:
    """Final assembled context for LLM."""
    excerpts: List[ContextExcerpt]
    citations: List[str]
    total_tokens: int
    truncated: bool
    summary: str


class ContextPacker:
    """Assembles final context from search hits."""
    
    def __init__(self, max_tokens: int = 8000):
        self.max_tokens = max_tokens
        self.package_root = Path(__file__).resolve().parents[3]
    
    def pack_context(self, hits: List[SearchHit], query: str) -> PackedContext:
        """
        Main packing function that assembles excerpts and citations.
        
        Args:
            hits: Search hits from hybrid retriever
            query: Original user query for context
            
        Returns:
            PackedContext with excerpts, citations, and metadata
        """
        # 1. Extract excerpts from hits
        excerpts = self._extract_excerpts(hits)
        
        # 2. Expand excerpts with surrounding context
        expanded_excerpts = self._expand_excerpts(excerpts)
        
        # 3. Deduplicate and rank excerpts
        unique_excerpts = self._dedupe_excerpts(expanded_excerpts)
        
        # 4. Fit within token budget
        final_excerpts, truncated = self._fit_token_budget(unique_excerpts)
        
        # 5. Generate citations
        citations = self._generate_citations(final_excerpts)
        
        # 6. Calculate total tokens and create summary
        total_tokens = self._estimate_tokens(final_excerpts)
        summary = self._create_summary(final_excerpts, query)
        
        return PackedContext(
            excerpts=final_excerpts,
            citations=citations,
            total_tokens=total_tokens,
            truncated=truncated,
            summary=summary
        )
    
    def _extract_excerpts(self, hits: List[SearchHit]) -> List[ContextExcerpt]:
        """Extract code/text excerpts from search hits."""
        excerpts = []
        
        for hit in hits:
            try:
                # Handle schema hits differently
                if hit.kind == "schema":
                    excerpts.append(ContextExcerpt(
                        project=hit.project,
                        path=hit.path,
                        content=hit.content,
                        start_line=1,
                        end_line=1,
                        hit_source=hit.source,
                        hit_score=hit.score
                    ))
                    continue
                
                # For file-based hits, extract actual content
                project_info = get_project_by_name(hit.project)
                if not project_info:
                    continue
                
                project_root = Path(project_info['root_path'])
                file_path = project_root / hit.path
                
                if not file_path.exists() or not file_path.is_file():
                    continue
                
                # Determine line range to extract
                if hit.start_line and hit.end_line:
                    start_line = max(1, hit.start_line)
                    end_line = hit.end_line
                else:
                    # Default to a reasonable excerpt around the hit
                    start_line = 1
                    end_line = 50  # Default excerpt size
                
                # Read the file content
                file_content = read_file(hit.project, str(file_path.relative_to(project_root)))
                if not file_content:
                    continue
                
                lines = file_content.split('\n')
                if start_line > len(lines):
                    continue
                
                end_line = min(end_line, len(lines))
                excerpt_lines = lines[start_line-1:end_line]
                excerpt_content = '\n'.join(excerpt_lines)
                
                excerpts.append(ContextExcerpt(
                    project=hit.project,
                    path=hit.path,
                    content=excerpt_content,
                    start_line=start_line,
                    end_line=end_line,
                    hit_source=hit.source,
                    hit_score=hit.score
                ))
                
            except Exception as e:
                print(f"Warning: Failed to extract excerpt from {hit.path}: {e}")
                continue
        
        return excerpts
    
    def _expand_excerpts(self, excerpts: List[ContextExcerpt]) -> List[ContextExcerpt]:
        """Expand excerpts with surrounding context (±10 lines)."""
        expanded = []
        
        for excerpt in excerpts:
            try:
                # Skip schema excerpts
                if excerpt.path == "<schema>":
                    expanded.append(excerpt)
                    continue
                
                # Get expanded context
                project_info = get_project_by_name(excerpt.project)
                if not project_info:
                    expanded.append(excerpt)
                    continue
                
                project_root = Path(project_info['root_path'])
                file_path = project_root / excerpt.path
                
                if not file_path.exists():
                    expanded.append(excerpt)
                    continue
                
                # Read full file to expand context
                file_content = read_file(excerpt.project, excerpt.path)
                if not file_content:
                    expanded.append(excerpt)
                    continue
                
                lines = file_content.split('\n')
                
                # Expand by ±10 lines
                expanded_start = max(1, excerpt.start_line - 10)
                expanded_end = min(len(lines), excerpt.end_line + 10)
                
                # Only expand if we're getting meaningful additional context
                if (expanded_start < excerpt.start_line or 
                    expanded_end > excerpt.end_line):
                    
                    expanded_lines = lines[expanded_start-1:expanded_end]
                    expanded_content = '\n'.join(expanded_lines)
                    
                    # Create expanded excerpt
                    expanded_excerpt = ContextExcerpt(
                        project=excerpt.project,
                        path=excerpt.path,
                        content=expanded_content,
                        start_line=expanded_start,
                        end_line=expanded_end,
                        hit_source=excerpt.hit_source,
                        hit_score=excerpt.hit_score,
                        expansion_context=True
                    )
                    expanded.append(expanded_excerpt)
                else:
                    expanded.append(excerpt)
                    
            except Exception as e:
                print(f"Warning: Failed to expand excerpt from {excerpt.path}: {e}")
                expanded.append(excerpt)
        
        return expanded
    
    def _dedupe_excerpts(self, excerpts: List[ContextExcerpt]) -> List[ContextExcerpt]:
        """Remove overlapping excerpts and rank by relevance."""
        if not excerpts:
            return []
        
        # Group by file
        by_file: Dict[str, List[ContextExcerpt]] = {}
        for excerpt in excerpts:
            key = f"{excerpt.project}:{excerpt.path}"
            if key not in by_file:
                by_file[key] = []
            by_file[key].append(excerpt)
        
        # Process each file separately
        deduped = []
        for file_excerpts in by_file.values():
            # Sort by score (highest first)
            file_excerpts.sort(key=lambda e: e.hit_score, reverse=True)
            
            file_deduped = []
            for excerpt in file_excerpts:
                # Check for overlap with existing excerpts
                overlaps = False
                for existing in file_deduped:
                    if self._excerpts_overlap(excerpt, existing):
                        overlaps = True
                        break
                
                if not overlaps:
                    file_deduped.append(excerpt)
                elif excerpt.hit_score > existing.hit_score * 1.2:
                    # Replace if significantly better score
                    file_deduped.remove(existing)
                    file_deduped.append(excerpt)
            
            deduped.extend(file_deduped)
        
        # Sort all excerpts by score
        deduped.sort(key=lambda e: e.hit_score, reverse=True)
        return deduped
    
    def _excerpts_overlap(self, a: ContextExcerpt, b: ContextExcerpt) -> bool:
        """Check if two excerpts from the same file overlap."""
        if a.path != b.path or a.project != b.project:
            return False
        
        # Check line range overlap
        return not (a.end_line < b.start_line or b.end_line < a.start_line)
    
    def _fit_token_budget(self, excerpts: List[ContextExcerpt]) -> Tuple[List[ContextExcerpt], bool]:
        """Fit excerpts within token budget."""
        final_excerpts = []
        current_tokens = 0
        truncated = False
        
        # Reserve tokens for formatting and citations
        available_tokens = self.max_tokens - 500
        
        for excerpt in excerpts:
            excerpt_tokens = self._estimate_excerpt_tokens(excerpt)
            
            if current_tokens + excerpt_tokens <= available_tokens:
                final_excerpts.append(excerpt)
                current_tokens += excerpt_tokens
            else:
                # Try to fit a truncated version
                remaining_tokens = available_tokens - current_tokens
                if remaining_tokens > 100:  # Only if meaningful space left
                    truncated_excerpt = self._truncate_excerpt(excerpt, remaining_tokens)
                    if truncated_excerpt:
                        final_excerpts.append(truncated_excerpt)
                        current_tokens += self._estimate_excerpt_tokens(truncated_excerpt)
                
                truncated = True
                break
        
        return final_excerpts, truncated
    
    def _estimate_excerpt_tokens(self, excerpt: ContextExcerpt) -> int:
        """Estimate token count for an excerpt."""
        # Rough estimate: 1 token ≈ 4 characters
        content_tokens = len(excerpt.content) // 4
        
        # Add tokens for formatting
        formatting_tokens = 50  # For file header, line numbers, etc.
        
        return content_tokens + formatting_tokens
    
    def _truncate_excerpt(self, excerpt: ContextExcerpt, max_tokens: int) -> Optional[ContextExcerpt]:
        """Truncate excerpt to fit token budget."""
        if max_tokens < 100:
            return None
        
        # Estimate max characters
        max_chars = (max_tokens - 50) * 4  # Reserve 50 tokens for formatting
        
        if len(excerpt.content) <= max_chars:
            return excerpt
        
        # Truncate content, try to break at line boundaries
        lines = excerpt.content.split('\n')
        truncated_lines = []
        current_chars = 0
        
        for line in lines:
            if current_chars + len(line) + 1 <= max_chars:
                truncated_lines.append(line)
                current_chars += len(line) + 1
            else:
                truncated_lines.append("... [truncated]")
                break
        
        if not truncated_lines:
            return None
        
        truncated_content = '\n'.join(truncated_lines)
        return ContextExcerpt(
            project=excerpt.project,
            path=excerpt.path,
            content=truncated_content,
            start_line=excerpt.start_line,
            end_line=excerpt.start_line + len(truncated_lines) - 1,
            hit_source=excerpt.hit_source,
            hit_score=excerpt.hit_score,
            expansion_context=excerpt.expansion_context
        )
    
    def _generate_citations(self, excerpts: List[ContextExcerpt]) -> List[str]:
        """Generate citation strings for excerpts."""
        citations = []
        
        for i, excerpt in enumerate(excerpts, 1):
            if excerpt.path == "<schema>":
                citation = f"[{i}] Schema: {excerpt.content[:50]}..."
            else:
                lines_part = ""
                if excerpt.start_line == excerpt.end_line:
                    lines_part = f":{excerpt.start_line}"
                elif excerpt.end_line > excerpt.start_line:
                    lines_part = f":{excerpt.start_line}-{excerpt.end_line}"
                
                citation = f"[{i}] {excerpt.path}{lines_part} (via {excerpt.hit_source})"
            
            citations.append(citation)
        
        return citations
    
    def _estimate_tokens(self, excerpts: List[ContextExcerpt]) -> int:
        """Estimate total token count."""
        total = 0
        for excerpt in excerpts:
            total += self._estimate_excerpt_tokens(excerpt)
        return total
    
    def _create_summary(self, excerpts: List[ContextExcerpt], query: str) -> str:
        """Create a summary of the packed context."""
        if not excerpts:
            return "No relevant context found"
        
        file_count = len(set(e.path for e in excerpts))
        source_counts = {}
        for e in excerpts:
            source_counts[e.hit_source] = source_counts.get(e.hit_source, 0) + 1
        
        sources_summary = ", ".join([f"{count} from {source}" 
                                   for source, count in source_counts.items()])
        
        return (f"Found {len(excerpts)} excerpts from {file_count} files "
                f"({sources_summary}) for query: {query[:50]}")


# Convenience functions
def pack_context(hits: List[SearchHit], query: str, max_tokens: int = 8000) -> PackedContext:
    """Pack search hits into context for LLM."""
    packer = ContextPacker(max_tokens)
    return packer.pack_context(hits, query)


def format_context_for_llm(packed_context: PackedContext) -> str:
    """Format packed context as string for LLM input."""
    lines = []
    
    # Add summary
    lines.append(f"# Context Summary")
    lines.append(packed_context.summary)
    lines.append("")
    
    # Add excerpts
    lines.append("# Relevant Code/Documentation")
    lines.append("")
    
    for i, excerpt in enumerate(packed_context.excerpts, 1):
        if excerpt.path == "<schema>":
            lines.append(f"## [{i}] Database Schema")
            lines.append(excerpt.content)
        else:
            lines.append(f"## [{i}] {excerpt.path}:{excerpt.start_line}-{excerpt.end_line}")
            lines.append("```")
            lines.append(excerpt.content)
            lines.append("```")
        
        lines.append("")
    
    # Add citations
    if packed_context.citations:
        lines.append("# Citations")
        for citation in packed_context.citations:
            lines.append(citation)
        lines.append("")
    
    # Add metadata
    lines.append(f"# Context Metadata")
    lines.append(f"- Total tokens: ~{packed_context.total_tokens}")
    lines.append(f"- Excerpts: {len(packed_context.excerpts)}")
    lines.append(f"- Truncated: {packed_context.truncated}")
    
    return "\n".join(lines)
