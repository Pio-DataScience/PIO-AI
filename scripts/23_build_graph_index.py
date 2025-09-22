#!/usr/bin/env python3
"""
Script to build call & import graph index for a project.
"""

import sys
import os
from pathlib import Path
import argparse
import time

# Add the parent directory (PIO-AI root) to Python path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from services.indexer.graph_index import GraphIndexer, build_project_graph
from services.ingest.manifest_reader import read_manifest, get_project_by_name
from services.tools_api.ast_tools import sanitize_project_name


def main():
    parser = argparse.ArgumentParser(description="Build call & import graph index")
    parser.add_argument("project", help="Project name from manifest.yaml")
    parser.add_argument("--force", action="store_true", help="Force rebuild existing index")
    parser.add_argument("--verbose", "-v", action="store_true", help="Verbose output")
    
    args = parser.parse_args()
    
    try:
        print(f"🔗 Building graph index for project: {args.project}")
        
        # Load project info
        project_info = get_project_by_name(args.project)
        if not project_info:
            print(f"❌ Project '{args.project}' not found in manifest.yaml")
            return 1
        
        project_root = Path(project_info["root_path"])
        if not project_root.exists():
            print(f"❌ Project root does not exist: {project_root}")
            return 1
        
        # Check if index already exists
        package_root = Path(__file__).resolve().parents[1]
        sanitized_name = sanitize_project_name(args.project)
        graph_db = package_root / "indexes" / "graph" / f"{sanitized_name}.sqlite"
        
        if graph_db.exists() and not args.force:
            print(f"⚠️ Graph index already exists: {graph_db}")
            print("Use --force to rebuild")
            return 0
        
        # Create indexer
        indexer = GraphIndexer()
        
        # Build the graph
        start_time = time.time()
        
        # Get project info to build properly
        project_root = Path(project_info["root_path"])
        includes = project_info.get("include", ["**/*.py"])
        excludes = project_info.get("exclude", [])
        
        # Build graph index
        stats = build_project_graph(args.project, project_root, includes, excludes, graph_db)
        elapsed = time.time() - start_time
        
        # Print results
        print(f"\n✅ Graph index built successfully!")
        print(f"📊 Statistics:")
        print(f"   - Files processed: {stats['files']}")
        print(f"   - Import relationships: {stats['imports']}")
        print(f"   - Call relationships: {stats['calls']}")
        print(f"   - Time: {elapsed:.2f}s")
        print(f"📁 Index saved to: {graph_db}")
        
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