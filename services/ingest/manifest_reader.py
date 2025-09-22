"""
Manifest reader for project configuration.
"""

import yaml
from pathlib import Path
from typing import List, Dict, Any

# Import the package root
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

# Use the PACKAGE_ROOT from __init__.py
from __init__ import PACKAGE_ROOT


def read_manifest() -> Dict[str, Any]:
    """Read the warehouse manifest.yaml file."""
    manifest_path = PACKAGE_ROOT / "warehouse" / "manifest.yaml"
    
    if not manifest_path.exists():
        raise FileNotFoundError(f"Manifest not found: {manifest_path}")
    
    with open(manifest_path, 'r', encoding='utf-8') as f:
        return yaml.safe_load(f)


def get_projects() -> List[Dict[str, Any]]:
    """Get list of projects from manifest."""
    manifest = read_manifest()
    return manifest.get("projects", [])


def get_project_by_name(project_name: str) -> Dict[str, Any]:
    """Get a specific project by name."""
    projects = get_projects()
    for project in projects:
        if project.get("name") == project_name:
            return project
    
    raise ValueError(f"Project '{project_name}' not found in manifest")


def validate_project_paths() -> List[str]:
    """Validate all project paths exist. Returns list of missing paths."""
    missing = []
    projects = get_projects()
    
    for project in projects:
        name = project.get("name", "unknown")
        root_path = project.get("root_path")  # Fixed: was "root"
        
        if not root_path:
            missing.append(f"Project '{name}': missing root_path")
            continue
            
        path_obj = Path(root_path)
        if not path_obj.exists():
            missing.append(f"Project '{name}': root_path does not exist: {root_path}")
    
    return missing
