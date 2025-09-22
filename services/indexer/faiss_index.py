"""
FAISS Vector Index with stub embeddings for offline development.

Provides vector similarity search over code and text with:
- Separate code and text spaces
- Deterministic stub embeddings for offline development
- FAISS IndexFlatIP for cosine similarity
- SQLite metadata storage
"""

import sys
import os
import json
import sqlite3
import hashlib
from pathlib import Path
from typing import List, Dict, Any, Tuple, Optional, Literal
from dataclasses import dataclass
import numpy as np

# Add package to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from services.ingest.normalizer import normalize_path_to_posix, normalize_encoding, get_file_kind

try:
    import faiss
except ImportError:
    print("Warning: FAISS not installed. Install with: pip install faiss-cpu")
    faiss = None


@dataclass
class VectorSearchResult:
    """FAISS vector search result."""
    project: str
    path: str
    kind: str
    score: float
    preview: str
    span: Optional[Tuple[int, int]] = None  # (start_line, end_line) for code blocks


class StubEmbedder:
    """Deterministic stub embeddings for offline development."""
    
    def __init__(self, dimension: int = 384):
        self.dimension = dimension
        
    def embed_texts(self, texts: List[str], space: Literal["code", "text"]) -> np.ndarray:
        """
        Generate deterministic embeddings based on text content.
        
        Args:
            texts: List of text strings to embed
            space: "code" or "text" space for different embedding behaviors
            
        Returns:
            Normalized embedding vectors
        """
        embeddings = []
        
        for text in texts:
            # Create deterministic hash-based embedding
            embedding = self._text_to_vector(text, space)
            embeddings.append(embedding)
        
        embeddings = np.array(embeddings, dtype=np.float32)
        
        # Normalize for cosine similarity
        norms = np.linalg.norm(embeddings, axis=1, keepdims=True)
        norms = np.where(norms == 0, 1, norms)  # Avoid division by zero
        embeddings = embeddings / norms
        
        return embeddings
    
    def _text_to_vector(self, text: str, space: str) -> np.ndarray:
        """Convert text to deterministic vector."""
        # Different seeds for code vs text spaces
        seed = hash(space) % 2**32
        
        # Use text content to create deterministic vector
        text_bytes = text.encode('utf-8')
        
        # Create multiple hash-based components
        vector_components = []
        
        for i in range(0, self.dimension, 4):  # Process in chunks of 4
            # Use different salt for each component
            salt = f"{seed}_{i}_{space}".encode('utf-8')
            hash_input = text_bytes + salt
            
            # Generate hash and convert to floats
            hash_obj = hashlib.sha256(hash_input)
            hash_bytes = hash_obj.digest()
            
            # Convert bytes to float values
            for j in range(min(4, self.dimension - i)):
                if j * 8 + 7 < len(hash_bytes):
                    # Use 8 bytes to create a float
                    byte_chunk = hash_bytes[j*8:(j+1)*8]
                    # Convert to signed integer then normalize
                    int_val = int.from_bytes(byte_chunk, byteorder='big', signed=True)
                    float_val = int_val / (2**63)  # Normalize to [-1, 1]
                    vector_components.append(float_val)
        
        # Pad if necessary
        while len(vector_components) < self.dimension:
            vector_components.append(0.0)
        
        # Truncate if necessary
        vector_components = vector_components[:self.dimension]
        
        # Add some code/text space specific transformations
        vector = np.array(vector_components, dtype=np.float32)
        
        if space == "code":
            # Code embeddings: emphasize structure, keywords
            vector = np.tanh(vector * 2.0)  # More concentrated
        else:
            # Text embeddings: more distributed 
            vector = np.tanh(vector * 0.8)  # More spread out
        
        return vector


class FAISSIndexer:
    """FAISS vector indexer with stub embeddings."""
    
    def __init__(self, dimension: int = 384):
        self.dimension = dimension
        self.embedder = StubEmbedder(dimension)
        
    def build_faiss_for_project(self, project_name: str, 
                               items: List[Tuple[Path, str, str]], 
                               out_dir_code: Path, 
                               out_dir_text: Path) -> Dict[str, int]:
        """
        Build FAISS indexes for a project.
        
        Args:
            project_name: Project name
            items: List of (abs_path, rel_posix, kind) tuples
            out_dir_code: Output directory for code index
            out_dir_text: Output directory for text index
            
        Returns:
            Statistics dictionary
        """
        # Separate items by kind
        code_items = [(p, r, k) for p, r, k in items if k == "code"]
        text_items = [(p, r, k) for p, r, k in items if k == "text"]
        
        stats = {'code_items': 0, 'text_items': 0, 'total_vectors': 0}
        
        # Build code index
        if code_items:
            stats['code_items'] = self._build_space_index(
                project_name, code_items, out_dir_code, "code"
            )
        
        # Build text index
        if text_items:
            stats['text_items'] = self._build_space_index(
                project_name, text_items, out_dir_text, "text"
            )
        
        stats['total_vectors'] = stats['code_items'] + stats['text_items']
        
        return stats
    
    def _build_space_index(self, project_name: str, 
                          items: List[Tuple[Path, str, str]], 
                          out_dir: Path, 
                          space: str) -> int:
        """Build FAISS index for one space (code or text)."""
        if not faiss:
            print(f"Warning: FAISS not available, skipping {space} index")
            return 0
        
        out_dir.mkdir(parents=True, exist_ok=True)
        
        # Prepare texts and metadata
        texts = []
        metadata = []
        
        for abs_path, rel_posix, kind in items:
            try:
                content = normalize_encoding(abs_path)
                
                # For code files, we might want to split into chunks
                if space == "code" and len(content) > 2000:
                    chunks = self._split_code_content(content)
                    for i, chunk in enumerate(chunks):
                        texts.append(chunk)
                        metadata.append({
                            'project': project_name,
                            'path': rel_posix,
                            'kind': kind,
                            'span': None,  # Could add line numbers later
                            'preview': chunk[:200] + "..." if len(chunk) > 200 else chunk,
                            'chunk_index': i
                        })
                else:
                    texts.append(content)
                    preview = content[:200] + "..." if len(content) > 200 else content
                    metadata.append({
                        'project': project_name,
                        'path': rel_posix,
                        'kind': kind,
                        'span': None,
                        'preview': preview,
                        'chunk_index': 0
                    })
                    
            except Exception as e:
                print(f"Warning: Could not process {abs_path}: {e}")
        
        if not texts:
            return 0
        
        # Generate embeddings
        embeddings = self.embedder.embed_texts(texts, space)
        
        # Create FAISS index
        index = faiss.IndexFlatIP(self.dimension)  # Inner product (cosine after normalization)
        index.add(embeddings)
        
        # Save index
        faiss.write_index(index, str(out_dir / "index.faiss"))
        
        # Save metadata to SQLite
        self._save_metadata(metadata, out_dir / "metadata.db")
        
        return len(texts)
    
    def _split_code_content(self, content: str) -> List[str]:
        """Split code content into semantic chunks."""
        lines = content.split('\n')
        chunks = []
        current_chunk = []
        current_size = 0
        
        for line in lines:
            # Start new chunk on class/function definitions or when size limit reached
            if (line.strip().startswith(('class ', 'def ', 'async def ')) and 
                current_chunk and current_size > 500):
                chunks.append('\n'.join(current_chunk))
                current_chunk = []
                current_size = 0
            
            current_chunk.append(line)
            current_size += len(line)
            
            # Hard size limit
            if current_size > 2000:
                chunks.append('\n'.join(current_chunk))
                current_chunk = []
                current_size = 0
        
        if current_chunk:
            chunks.append('\n'.join(current_chunk))
        
        return chunks
    
    def _save_metadata(self, metadata: List[Dict], db_path: Path):
        """Save metadata to SQLite database."""
        con = sqlite3.connect(db_path)
        con.execute("PRAGMA journal_mode=WAL")
        
        # Create metadata table
        con.execute("""
            CREATE TABLE IF NOT EXISTS metadata (
                id INTEGER PRIMARY KEY,
                project TEXT NOT NULL,
                path TEXT NOT NULL,
                kind TEXT NOT NULL,
                span_start INTEGER,
                span_end INTEGER,
                preview TEXT,
                chunk_index INTEGER DEFAULT 0
            )
        """)
        
        # Clear existing data for this project
        if metadata:
            project_name = metadata[0]['project']
            con.execute("DELETE FROM metadata WHERE project = ?", (project_name,))
        
        # Insert metadata
        for i, meta in enumerate(metadata):
            span = meta.get('span')
            span_start = span[0] if span else None
            span_end = span[1] if span else None
            
            con.execute("""
                INSERT INTO metadata (id, project, path, kind, span_start, span_end, preview, chunk_index)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (i, meta['project'], meta['path'], meta['kind'], 
                  span_start, span_end, meta['preview'], meta.get('chunk_index', 0)))
        
        con.commit()
        con.close()
    
    def search_faiss(self, project_name: str, query: str, space: Literal["code", "text"], 
                     top_k: int = 10) -> List[VectorSearchResult]:
        """
        Search FAISS index.
        
        Args:
            project_name: Project to search
            query: Search query
            space: "code" or "text" space
            top_k: Number of results
            
        Returns:
            List of search results
        """
        if not faiss:
            return []
        
        # Get index directory
        package_root = Path(__file__).resolve().parents[3]
        if space == "code":
            index_dir = package_root / "indexes" / "faiss_code" / project_name
        else:
            index_dir = package_root / "indexes" / "faiss_text" / project_name
        
        index_path = index_dir / "index.faiss"
        metadata_path = index_dir / "metadata.db"
        
        if not index_path.exists() or not metadata_path.exists():
            return []
        
        try:
            # Load index
            index = faiss.read_index(str(index_path))
            
            # Generate query embedding
            query_embedding = self.embedder.embed_texts([query], space)
            
            # Search
            scores, indices = index.search(query_embedding, min(top_k, index.ntotal))
            
            # Load metadata
            con = sqlite3.connect(metadata_path)
            
            results = []
            for score, idx in zip(scores[0], indices[0]):
                if idx == -1:  # No more results
                    break
                
                cursor = con.execute("""
                    SELECT project, path, kind, span_start, span_end, preview
                    FROM metadata WHERE id = ?
                """, (int(idx),))
                
                row = cursor.fetchone()
                if row:
                    span = None
                    if row[3] is not None and row[4] is not None:
                        span = (row[3], row[4])
                    
                    results.append(VectorSearchResult(
                        project=row[0],
                        path=row[1],
                        kind=row[2],
                        score=float(score),
                        preview=row[5],
                        span=span
                    ))
            
            con.close()
            return results
            
        except Exception as e:
            print(f"Error searching FAISS index: {e}")
            return []


# Convenience functions
def build_faiss_for_project(project_name: str, items: List[Tuple[Path, str, str]], 
                           out_dir_code: Path, out_dir_text: Path) -> Dict[str, int]:
    """Convenience function to build FAISS indexes."""
    indexer = FAISSIndexer()
    return indexer.build_faiss_for_project(project_name, items, out_dir_code, out_dir_text)


def search_faiss(project_name: str, query: str, space: Literal["code", "text"], 
                top_k: int = 10) -> List[Dict[str, Any]]:
    """Convenience function to search FAISS index."""
    indexer = FAISSIndexer()
    results = indexer.search_faiss(project_name, query, space, top_k)
    
    return [
        {
            'project': r.project,
            'path': r.path,
            'kind': r.kind,
            'score': r.score,
            'preview': r.preview,
            'span': r.span
        }
        for r in results
    ]


def embed_texts(texts: List[str], space: Literal["code", "text"]) -> np.ndarray:
    """Generate embeddings for texts (stub implementation)."""
    embedder = StubEmbedder()
    return embedder.embed_texts(texts, space)