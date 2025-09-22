#!/usr/bin/env python3
"""
Script to build FAISS vector search index for a project.
"""

import sys
import os
from pathlib import Path
import argparse
import time

# Add the parent directory (PIO-AI root) to Python path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from services.indexer.faiss_index import FAISSIndexer, build_project_index
from services.ingest.manifest_reader import read_manifest, get_project_by_name
from services.tools_api.ast_tools import sanitize_project_name


def main():
    parser = argparse.ArgumentParser(description="Build FAISS vector search index")
    parser.add_argument("project", help="Project name from manifest.yaml")
    parser.add_argument("--force", action="store_true", help="Force rebuild existing index")
    parser.add_argument("--verbose", "-v", action="store_true", help="Verbose output")
    parser.add_argument("--space", choices=["both", "code", "text"], default="both",
                       help="Which vector space to build (default: both)")
    
    args = parser.parse_args()
    
    try:
        print(f"🔢 Building FAISS index for project: {args.project}")
        print(f"🎯 Building vector space(s): {args.space}")
        
        # Load project info
        project_info = get_project_by_name(args.project)
        if not project_info:
            print(f"❌ Project '{args.project}' not found in manifest.yaml")
            return 1
        
        project_root = Path(project_info["root_path"])
        if not project_root.exists():
            print(f"❌ Project root does not exist: {project_root}")
            return 1
        
        # Check if indexes already exist
        package_root = Path(__file__).resolve().parents[1]
        sanitized_name = sanitize_project_name(args.project)
        
        code_index = package_root / "indexes" / "faiss_code" / f"{sanitized_name}.index"
        text_index = package_root / "indexes" / "faiss_text" / f"{sanitized_name}.index"
        
        if not args.force:
            if args.space in ["both", "code"] and code_index.exists():
                print(f"⚠️ Code FAISS index already exists: {code_index}")
                if args.space == "code":
                    print("Use --force to rebuild")
                    return 0
            
            if args.space in ["both", "text"] and text_index.exists():
                print(f"⚠️ Text FAISS index already exists: {text_index}")
                if args.space == "text":
                    print("Use --force to rebuild")
                    return 0
        
        # Create indexer
        indexer = FAISSIndexer()
        
        # Build the index(es)
        start_time = time.time()
        
        total_stats = {
            "files_processed": 0,
            "code_chunks": 0,
            "text_chunks": 0,
            "total_vectors": 0
        }
        
        if args.space in ["both", "code"]:
            print(f"\n📝 Building code vector space...")
            code_stats = build_project_index(args.project, "code", verbose=args.verbose)
            total_stats["files_processed"] += code_stats["files_processed"]
            total_stats["code_chunks"] = code_stats["total_chunks"]
            total_stats["total_vectors"] += code_stats["total_chunks"]
        
        if args.space in ["both", "text"]:
            print(f"\n📄 Building text vector space...")
            text_stats = build_project_index(args.project, "text", verbose=args.verbose)
            if args.space == "text":
                total_stats["files_processed"] = text_stats["files_processed"]
            total_stats["text_chunks"] = text_stats["total_chunks"]
            total_stats["total_vectors"] += text_stats["total_chunks"]
        
        elapsed = time.time() - start_time
        
        # Print results
        print(f"\n✅ FAISS index built successfully!")
        print(f"📊 Statistics:")
        print(f"   - Files processed: {total_stats['files_processed']}")
        if total_stats["code_chunks"] > 0:
            print(f"   - Code chunks: {total_stats['code_chunks']}")
        if total_stats["text_chunks"] > 0:
            print(f"   - Text chunks: {total_stats['text_chunks']}")
        print(f"   - Total vectors: {total_stats['total_vectors']}")
        print(f"   - Time: {elapsed:.2f}s")
        
        if args.space in ["both", "code"]:
            print(f"📁 Code index: {code_index}")
        if args.space in ["both", "text"]:
            print(f"📁 Text index: {text_index}")
        
        # Test the index
        print(f"\n🧪 Testing search functionality...")
        try:
            from services.indexer.faiss_index import search_faiss
            if args.space in ["both", "code"]:
                code_results = search_faiss(args.project, "function", "code", max_results=3)
                print(f"   - Code search found {len(code_results)} results")
            if args.space in ["both", "text"]:
                text_results = search_faiss(args.project, "documentation", "text", max_results=3)
                print(f"   - Text search found {len(text_results)} results")
        except Exception as e:
            print(f"   - Test search failed: {e}")
        
        return 0
        
    except KeyboardInterrupt:
        print("\n❌ Interrupted by user")
        return 130
    except Exception as e:
        print(f"❌ Error: {e}")
        if args.verbose:
            import traceback
            traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())