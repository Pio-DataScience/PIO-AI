#!/usr/bin/env python3
"""
Script to serve the RAG API using FastAPI.
"""

import sys
import os
from pathlib import Path
import argparse

# Add the parent directory (PIO-AI root) to Python path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main():
    parser = argparse.ArgumentParser(description="Serve the PIO-AI RAG API")
    parser.add_argument("--host", default="0.0.0.0", help="Host to bind to (default: 0.0.0.0)")
    parser.add_argument("--port", type=int, default=8080, help="Port to bind to (default: 8080)")
    parser.add_argument("--reload", action="store_true", help="Enable auto-reload for development")
    parser.add_argument("--debug", action="store_true", help="Enable debug mode")
    parser.add_argument("--workers", type=int, default=1, help="Number of worker processes")
    
    args = parser.parse_args()
    
    try:
        # Set environment variables
        os.environ["API_HOST"] = args.host
        os.environ["API_PORT"] = str(args.port)
        if args.debug:
            os.environ["DEBUG"] = "true"
        
        # Import and check dependencies
        try:
            import uvicorn
        except ImportError:
            print("❌ uvicorn not installed. Run: pip install uvicorn")
            return 1
        
        try:
            from fastapi import FastAPI
        except ImportError:
            print("❌ FastAPI not installed. Run: pip install fastapi")
            return 1
        
        # Check if server module exists
        server_path = Path(__file__).parent.parent / "services" / "api" / "server.py"
        if not server_path.exists():
            print(f"❌ Server module not found: {server_path}")
            return 1
        
        print(f"🚀 Starting PIO-AI RAG API...")
        print(f"📍 Address: http://{args.host}:{args.port}")
        print(f"📚 Documentation: http://{args.host}:{args.port}/docs")
        print(f"🔍 Interactive docs: http://{args.host}:{args.port}/redoc")
        
        if args.debug:
            print(f"🐛 Debug mode enabled")
        if args.reload:
            print(f"🔄 Auto-reload enabled")
        
        # Run the server
        uvicorn.run(
            "services.api.server:app",
            host=args.host,
            port=args.port,
            reload=args.reload,
            workers=args.workers if not args.reload else 1,  # Can't use workers with reload
            log_level="debug" if args.debug else "info",
            access_log=args.debug
        )
        
        return 0
        
    except KeyboardInterrupt:
        print("\n👋 Server stopped by user")
        return 0
    except Exception as e:
        print(f"❌ Error starting server: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())