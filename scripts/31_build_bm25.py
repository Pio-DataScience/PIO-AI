#!/usr/bin/env python3
"""
Script to build BM25 keyword search index for a project.
"""

import sys
import os
from pathlib import Path
import argparse
import time

# Add the parent directory (PIO-AI root) to Python path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from services.indexer.bm25_index import BM25Indexer, build_bm25_for_project, prepare_files_for_indexing
from services.ingest.manifest_reader import read_manifest, get_project_by_name


def sanitize_project_name(name: str) -> str:
    """Sanitize project name for use as directory name."""
    return name.replace(" ", "_").replace("-", "_").lower()


def main():
    parser = argparse.ArgumentParser(description="Build BM25 keyword search index")
    parser.add_argument("project", help="Project name from manifest.yaml")
    parser.add_argument("--force", action="store_true", help="Force rebuild existing index")
    parser.add_argument("--verbose", "-v", action="store_true", help="Verbose output")
    
    args = parser.parse_args()
    
    try:
        print(f"Building BM25 index for project: {args.project}")
        
        # Load project info
        project_info = get_project_by_name(args.project)
        if not project_info:
            print(f"Project '{args.project}' not found in manifest.yaml")
            return 1
        
        project_root = Path(project_info["root_path"])
        if not project_root.exists():
            print(f"Project root does not exist: {project_root}")
            return 1
        
        # Check if index already exists
        package_root = Path(__file__).resolve().parents[1]
        sanitized_name = sanitize_project_name(args.project)
        index_dir = package_root / "indexes" / "bm25" / sanitized_name
        
        if index_dir.exists() and not args.force:
            print(f"⚠️ BM25 index already exists: {index_dir}")
            print("Use --force to rebuild")
            return 0
        
        # Create indexer
        indexer = BM25Indexer()
        
        # Prepare files for indexing
        files = prepare_files_for_indexing(
            project_root, 
            project_info.get("includes", ["**/*.py", "**/*.md", "**/*.txt"]),
            project_info.get("excludes", ["**/.*", "**/__pycache__/**", "**/node_modules/**"])
        )
        
        if args.verbose:
            print(f"Found {len(files)} files to index")
        
        # Build the index
        start_time = time.time()
        stats = build_bm25_for_project(args.project, files, index_dir)
        elapsed = time.time() - start_time
        
        # Print results
        print(f"\nBM25 index built successfully!")
        print(f"Statistics:")
        print(f"   - Files processed: {stats['files']}")
        print(f"   - Code files: {stats['code_files']}")
        print(f"   - Text files: {stats['text_files']}")
        print(f"   - Total characters: {stats['total_chars']:,}")
        print(f"   - Time: {elapsed:.2f}s")
        print(f"Index saved to: {index_dir}")
        
        # Test the index
        print(f"\n🧪 Testing search functionality...")
        try:
            from services.indexer.bm25_index import search_bm25
            test_results = search_bm25(args.project, "function", top_k=3)
            print(f"   - Test search found {len(test_results)} results")
        except Exception as e:
            print(f"   - Test search failed: {e}")
        
        return 0
        
    except KeyboardInterrupt:
        print("\nInterrupted by user")
        return 130
    except Exception as e:
        print(f"Error: {e}")
        if args.verbose:
            import traceback
            traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())