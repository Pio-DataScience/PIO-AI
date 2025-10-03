"""
Production AML API Server Launcher
"""

import os
import sys
from pathlib import Path

# Ensure we're in the correct directory
script_dir = Path(__file__).parent
os.chdir(script_dir)

# Add the project root to Python path
project_root = script_dir
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

print(f"Working directory: {os.getcwd()}")
print(f"Python path includes: {project_root}")

# Now import and run the server
try:
    from services.api.server import app
    import uvicorn
    
    # Configuration
    host = os.getenv("API_HOST", "127.0.0.1")
    port = int(os.getenv("API_PORT", "8090"))  # Changed to different port
    debug = os.getenv("DEBUG", "false").lower() == "true"
    
    print(f"Starting PIO-AI Production AML API on {host}:{port}")
    print(f"Documentation available at http://{host}:{port}/docs")
    print(f"Interactive API at http://{host}:{port}/redoc")
    
    uvicorn.run(
        app,
        host=host,
        port=port,
        reload=debug,
        log_level="info" if not debug else "debug"
    )
    
except ImportError as e:
    print(f"Import error: {e}")
    print(f"Current working directory: {os.getcwd()}")
    print(f"Python path: {sys.path}")
    sys.exit(1)
except Exception as e:
    print(f"Error starting server: {e}")
    sys.exit(1)