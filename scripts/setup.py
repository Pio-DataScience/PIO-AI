#!/usr/bin/env python3
"""
Setup script for PIO-AI RAG system.
Helps with initial configuration and dependency installation.
"""

import sys
import os
import subprocess
from pathlib import Path
import shutil


def print_section(title):
    """Print a section header."""
    print(f"\n{'='*60}")
    print(f"🚀 {title}")
    print('='*60)


def check_python_version():
    """Check Python version."""
    print("🐍 Checking Python version...")
    version = sys.version_info
    if version.major < 3 or (version.major == 3 and version.minor < 10):
        print(f"❌ Python 3.10+ required, got {version.major}.{version.minor}")
        return False
    print(f"✅ Python {version.major}.{version.minor}.{version.micro}")
    return True


def create_env_file():
    """Create .env file from template."""
    print("📝 Setting up environment configuration...")
    
    package_root = Path(__file__).parent.parent
    template_path = package_root / "config" / ".env.template"
    env_path = package_root / "config" / ".env"
    
    if env_path.exists():
        print("✅ .env file already exists")
        return True
    
    if not template_path.exists():
        print("❌ .env.template not found")
        return False
    
    try:
        shutil.copy(template_path, env_path)
        print(f"✅ Created .env file from template")
        print(f"📁 Location: {env_path}")
        print("⚠️ Please edit the .env file to configure your API keys")
        return True
    except Exception as e:
        print(f"❌ Error creating .env file: {e}")
        return False


def install_dependencies():
    """Install required dependencies."""
    print("📦 Installing dependencies...")
    
    # Core dependencies
    core_deps = [
        "pyyaml",
        "python-dotenv",
        "rich",  # For better CLI experience
    ]
    
    # Optional dependencies based on features used
    optional_deps = {
        "whoosh": "BM25 search indexing",
        "faiss-cpu": "Vector search (CPU version)",
        "numpy": "Vector operations", 
        "cohere": "Cohere LLM provider",
        "openai": "OpenAI/Azure OpenAI providers",
        "fastapi": "API server",
        "uvicorn": "API server runtime",
        "requests": "HTTP requests",
    }
    
    print("Installing core dependencies...")
    for dep in core_deps:
        try:
            subprocess.check_call([sys.executable, "-m", "pip", "install", dep], 
                                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            print(f"✅ {dep}")
        except subprocess.CalledProcessError:
            print(f"❌ Failed to install {dep}")
    
    print("\nOptional dependencies (install as needed):")
    for dep, description in optional_deps.items():
        try:
            __import__(dep.replace('-', '_'))
            print(f"✅ {dep} - {description}")
        except ImportError:
            print(f"⚠️ {dep} - {description} (not installed)")
    
    print(f"\n💡 To install all optional dependencies:")
    print(f"pip install {' '.join(optional_deps.keys())}")


def create_directories():
    """Create required directories."""
    print("📁 Creating directory structure...")
    
    package_root = Path(__file__).parent.parent
    dirs_to_create = [
        "indexes/symbols",
        "indexes/graph", 
        "indexes/bm25",
        "indexes/faiss_code",
        "indexes/faiss_text",
        "logs",
    ]
    
    for dir_path in dirs_to_create:
        full_path = package_root / dir_path
        full_path.mkdir(parents=True, exist_ok=True)
        print(f"✅ {dir_path}")


def check_manifest():
    """Check if manifest.yaml exists."""
    print("📋 Checking project manifest...")
    
    package_root = Path(__file__).parent.parent
    manifest_path = package_root / "warehouse" / "manifest.yaml"
    
    if manifest_path.exists():
        print(f"✅ Found manifest.yaml")
        try:
            import yaml
            with open(manifest_path) as f:
                manifest = yaml.safe_load(f)
            
            projects = manifest.get("projects", [])
            print(f"📊 {len(projects)} projects configured")
            
            for project in projects[:3]:  # Show first 3
                print(f"   • {project['name']}: {project['root_path']}")
            
            if len(projects) > 3:
                print(f"   ... and {len(projects) - 3} more")
            
            return True
        except Exception as e:
            print(f"⚠️ Error reading manifest: {e}")
            return False
    else:
        print(f"⚠️ No manifest.yaml found at {manifest_path}")
        print("💡 Create warehouse/manifest.yaml to configure your projects")
        return False


def test_llm_providers():
    """Test LLM provider configuration."""
    print("🤖 Testing LLM provider configuration...")
    
    try:
        sys.path.append(str(Path(__file__).parent.parent))
        from services.llm.provider import get_available_providers
        
        providers = get_available_providers()
        if providers:
            print(f"✅ Available providers: {', '.join(providers)}")
            return True
        else:
            print("⚠️ No LLM providers configured")
            print("💡 Add API keys to your .env file")
            return False
    except Exception as e:
        print(f"❌ Error testing providers: {e}")
        return False


def show_next_steps():
    """Show next steps to user."""
    print_section("Next Steps")
    
    print("🎯 To start using PIO-AI:")
    print()
    print("1. Configure your .env file:")
    print("   • Add your Cohere API key (already done!)")
    print("   • Or add OpenAI/Azure OpenAI keys if preferred")
    print()
    print("2. Set up your projects in warehouse/manifest.yaml")
    print()
    print("3. Build indexes for your projects:")
    print("   python scripts/21_build_ast_index.py <project_name>")
    print("   python scripts/23_build_graph_index.py <project_name>")
    print("   python scripts/31_build_bm25.py <project_name>")
    print("   python scripts/32_build_faiss.py <project_name>")
    print()
    print("4. Start chatting with your code:")
    print("   python scripts/chat.py")
    print("   # Or with a specific project:")
    print("   python scripts/chat.py --project <project_name>")
    print()
    print("5. Or start the API server:")
    print("   python scripts/40_serve_api.py")
    print()
    print("🎉 Happy coding with PIO-AI!")


def main():
    """Main setup function."""
    print_section("PIO-AI Setup")
    
    success = True
    
    # Check Python version
    if not check_python_version():
        success = False
    
    # Create directories
    create_directories()
    
    # Create .env file
    if not create_env_file():
        success = False
    
    # Install dependencies
    install_dependencies()
    
    # Check manifest
    check_manifest()
    
    # Test LLM providers
    test_llm_providers()
    
    # Show next steps
    show_next_steps()
    
    if success:
        print(f"\n✅ Setup completed successfully!")
    else:
        print(f"\n⚠️ Setup completed with some issues. Please review the messages above.")
    
    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())