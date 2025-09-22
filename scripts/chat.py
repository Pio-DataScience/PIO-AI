#!/usr/bin/env python3
"""
Command-line interface for PIO-AI RAG system.
Interactive chat with your codebase!
"""

import sys
import os
import argparse
from pathlib import Path

# Add the parent directory (PIO-AI root) to Python path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

try:
    from rich.console import Console
    from rich.panel import Panel
    from rich.text import Text
    from rich.prompt import Prompt
    from rich.markdown import Markdown
    from rich.table import Table
    from rich.progress import Progress, SpinnerColumn, TextColumn
    RICH_AVAILABLE = True
except ImportError:
    RICH_AVAILABLE = False
    print("⚠️ For better experience, install rich: pip install rich")

from services.llm.answer import answer_query, answer_with_context
from services.llm.provider import get_available_providers, set_provider
from services.ingest.manifest_reader import read_manifest


class PIOAICLI:
    """PIO-AI Command Line Interface."""
    
    def __init__(self):
        self.console = Console() if RICH_AVAILABLE else None
        self.current_project = None
        self.current_path = ""
        self.current_line = 0
        self.debug_mode = False
    
    def print(self, *args, **kwargs):
        """Print with rich if available, otherwise regular print."""
        if self.console:
            self.console.print(*args, **kwargs)
        else:
            print(*args, **kwargs)
    
    def print_panel(self, content, title="", style="blue"):
        """Print a panel with rich styling."""
        if self.console:
            self.console.print(Panel(content, title=title, border_style=style))
        else:
            print(f"\n=== {title} ===")
            print(content)
            print("=" * (len(title) + 8))
    
    def show_welcome(self):
        """Show welcome message."""
        if self.console:
            welcome_text = Text()
            welcome_text.append("🤖 Welcome to ", style="bold blue")
            welcome_text.append("PIO-AI", style="bold magenta")
            welcome_text.append(" RAG System!", style="bold blue")
            
            self.print_panel(welcome_text, "PIO-AI CLI", "magenta")
            self.print("\n💡 [bold yellow]Commands:[/bold yellow]")
            self.print("  [cyan]/help[/cyan] - Show available commands")
            self.print("  [cyan]/project <name>[/cyan] - Switch to a project")
            self.print("  [cyan]/projects[/cyan] - List available projects")
            self.print("  [cyan]/context <file> [line][/cyan] - Set file context")
            self.print("  [cyan]/debug[/cyan] - Toggle debug mode")
            self.print("  [cyan]/providers[/cyan] - Show LLM providers")
            self.print("  [cyan]/quit[/cyan] - Exit")
            self.print("\n💬 [bold green]Just type your question to start chatting![/bold green]")
        else:
            print("🤖 Welcome to PIO-AI RAG System!")
            print("\nCommands:")
            print("  /help - Show available commands")
            print("  /project <name> - Switch to a project")
            print("  /projects - List available projects")
            print("  /context <file> [line] - Set file context")
            print("  /debug - Toggle debug mode")
            print("  /providers - Show LLM providers")
            print("  /quit - Exit")
            print("\n💬 Just type your question to start chatting!")
    
    def show_status(self):
        """Show current status."""
        providers = get_available_providers()
        
        if self.console:
            table = Table(title="Current Status")
            table.add_column("Setting", style="cyan")
            table.add_column("Value", style="green")
            
            table.add_row("Project", self.current_project or "None")
            table.add_row("Context File", self.current_path or "None")
            table.add_row("Context Line", str(self.current_line) if self.current_line else "None")
            table.add_row("Debug Mode", "On" if self.debug_mode else "Off")
            table.add_row("Available Providers", ", ".join(providers) if providers else "None")
            
            self.console.print(table)
        else:
            print("\n=== Current Status ===")
            print(f"Project: {self.current_project or 'None'}")
            print(f"Context File: {self.current_path or 'None'}")
            print(f"Context Line: {self.current_line or 'None'}")
            print(f"Debug Mode: {'On' if self.debug_mode else 'Off'}")
            print(f"Available Providers: {', '.join(providers) if providers else 'None'}")
    
    def list_projects(self):
        """List available projects."""
        try:
            manifest = read_manifest()
            projects = manifest.get("projects", [])
            
            if not projects:
                self.print("[red]No projects found in manifest.yaml[/red]")
                return
            
            if self.console:
                table = Table(title="Available Projects")
                table.add_column("Name", style="cyan")
                table.add_column("Description", style="white")
                table.add_column("Path", style="dim")
                
                for project in projects:
                    table.add_row(
                        project["name"],
                        project.get("description", ""),
                        project["root_path"]
                    )
                
                self.console.print(table)
            else:
                print("\n=== Available Projects ===")
                for project in projects:
                    print(f"• {project['name']}: {project.get('description', '')}")
                    print(f"  Path: {project['root_path']}")
        
        except Exception as e:
            self.print(f"[red]Error loading projects: {e}[/red]")
    
    def set_project(self, project_name: str):
        """Set current project."""
        try:
            manifest = read_manifest()
            projects = manifest.get("projects", [])
            
            for project in projects:
                if project["name"] == project_name:
                    self.current_project = project_name
                    self.print(f"[green]✅ Switched to project: {project_name}[/green]")
                    return
            
            self.print(f"[red]❌ Project '{project_name}' not found[/red]")
            
        except Exception as e:
            self.print(f"[red]Error setting project: {e}[/red]")
    
    def set_context(self, args: list):
        """Set file context."""
        if not args:
            self.print("[red]Usage: /context <file> [line][/red]")
            return
        
        self.current_path = args[0]
        self.current_line = int(args[1]) if len(args) > 1 and args[1].isdigit() else 0
        
        context_msg = f"📁 Context set to: {self.current_path}"
        if self.current_line:
            context_msg += f" (line {self.current_line})"
        
        self.print(f"[green]{context_msg}[/green]")
    
    def show_providers(self):
        """Show LLM provider information."""
        providers = get_available_providers()
        
        if self.console:
            table = Table(title="LLM Providers")
            table.add_column("Provider", style="cyan")
            table.add_column("Status", style="green")
            
            all_providers = ["openai", "azure_openai", "cohere", "local"]
            for provider in all_providers:
                status = "✅ Available" if provider in providers else "❌ Not configured"
                table.add_row(provider.title().replace("_", " "), status)
            
            self.console.print(table)
        else:
            print("\n=== LLM Providers ===")
            all_providers = ["openai", "azure_openai", "cohere", "local"]
            for provider in all_providers:
                status = "✅ Available" if provider in providers else "❌ Not configured"
                print(f"{provider.title().replace('_', ' ')}: {status}")
    
    def process_command(self, user_input: str) -> str:
        """Process special commands. Returns 'exit' to quit, 'processed' if handled, or 'continue' for LLM."""
        if not user_input.startswith("/"):
            return 'continue'
        
        parts = user_input[1:].split()
        command = parts[0].lower() if parts else ""
        args = parts[1:]
        
        if command == "help":
            self.show_welcome()
            return 'processed'
        elif command == "status":
            self.show_status()
            return 'processed'
        elif command == "projects":
            self.list_projects()
            return 'processed'
        elif command == "project":
            if args:
                self.set_project(args[0])
            else:
                self.print("[red]Usage: /project <name>[/red]")
            return 'processed'
        elif command == "context":
            self.set_context(args)
            return 'processed'
        elif command == "debug":
            self.debug_mode = not self.debug_mode
            self.print(f"[yellow]Debug mode: {'On' if self.debug_mode else 'Off'}[/yellow]")
            return 'processed'
        elif command == "providers":
            self.show_providers()
            return 'processed'
        elif command in ["quit", "exit", "q"]:
            self.print("[yellow]👋 Goodbye![/yellow]")
            return 'exit'
        else:
            self.print(f"[red]Unknown command: {command}[/red]")
            self.print("[dim]Type /help for available commands[/dim]")
            return 'processed'
        
        return 'continue'
    
    def format_answer(self, response):
        """Format the answer response for display."""
        if self.console:
            # Main answer
            self.print_panel(
                Markdown(response["answer"]), 
                f"🤖 Answer ({response['query_type']})",
                "green"
            )
            
            # Citations if available
            if response.get("citations"):
                citations_text = "\n".join([f"• {cite}" for cite in response["citations"]])
                self.print_panel(citations_text, "📚 Sources", "blue")
            
            # Metadata in debug mode
            if self.debug_mode and response.get("debug"):
                debug_info = response["debug"]
                debug_text = f"""Search hits: {debug_info.get('search_hits', 'N/A')}
Context excerpts: {debug_info.get('context_excerpts', 'N/A')}
Context tokens: {debug_info.get('context_tokens', 'N/A')}
Total time: {debug_info.get('total_time', 0):.2f}s
Provider: {response.get('provider', 'N/A')}"""
                self.print_panel(debug_text, "🔍 Debug Info", "dim")
        
        else:
            print(f"\n🤖 Answer ({response['query_type']}):")
            print("=" * 50)
            print(response["answer"])
            
            if response.get("citations"):
                print("\n📚 Sources:")
                for cite in response["citations"]:
                    print(f"• {cite}")
            
            if self.debug_mode and response.get("debug"):
                debug_info = response["debug"]
                print(f"\n🔍 Debug Info:")
                print(f"Search hits: {debug_info.get('search_hits', 'N/A')}")
                print(f"Context excerpts: {debug_info.get('context_excerpts', 'N/A')}")
                print(f"Total time: {debug_info.get('total_time', 0):.2f}s")
    
    def chat_loop(self):
        """Main chat loop."""
        self.show_welcome()
        self.print()
        
        while True:
            try:
                # Get user input
                if self.console:
                    user_input = Prompt.ask("\n[bold cyan]You[/bold cyan]").strip()
                else:
                    user_input = input("\nYou: ").strip()
                
                if not user_input:
                    continue
                
                # Process commands
                command_result = self.process_command(user_input)
                if command_result == 'exit':
                    break
                elif command_result == 'processed':
                    continue  # Command was handled, don't process with LLM
                
                # Check if project is set
                if not self.current_project:
                    self.print("[red]⚠️ Please set a project first using /project <name>[/red]")
                    self.print("[dim]Use /projects to see available projects[/dim]")
                    continue
                
                # Show thinking indicator
                if self.console:
                    with Progress(
                        SpinnerColumn(),
                        TextColumn("[progress.description]{task.description}"),
                        console=self.console,
                        transient=True
                    ) as progress:
                        task = progress.add_task("🧠 Thinking...", total=None)
                        
                        # Get answer
                        response = answer_with_context(
                            user_input,
                            self.current_project,
                            self.current_path,
                            self.current_line
                        )
                        
                        progress.stop()
                else:
                    print("🧠 Thinking...")
                    response = answer_with_context(
                        user_input,
                        self.current_project,
                        self.current_path,
                        self.current_line
                    )
                
                # Display answer
                self.format_answer(response)
                
            except KeyboardInterrupt:
                self.print("\n[yellow]👋 Goodbye![/yellow]")
                break
            except Exception as e:
                self.print(f"[red]❌ Error: {e}[/red]")
                if self.debug_mode:
                    import traceback
                    self.print(f"[dim]{traceback.format_exc()}[/dim]")


def main():
    parser = argparse.ArgumentParser(description="PIO-AI Interactive CLI")
    parser.add_argument("--project", "-p", help="Set initial project")
    parser.add_argument("--debug", "-d", action="store_true", help="Enable debug mode")
    parser.add_argument("--provider", help="Set LLM provider")
    
    args = parser.parse_args()
    
    # Check if .env file exists
    env_path = Path(__file__).parent.parent / "config" / ".env"
    if not env_path.exists():
        print("⚠️ No .env file found. Please copy config/.env.template to config/.env and configure your API keys.")
        return 1
    
    # Create CLI instance
    cli = PIOAICLI()
    
    # Set initial options
    if args.debug:
        cli.debug_mode = True
    
    if args.provider:
        try:
            set_provider(args.provider)
            cli.print(f"[green]✅ Set provider to: {args.provider}[/green]")
        except Exception as e:
            cli.print(f"[red]❌ Error setting provider: {e}[/red]")
    
    if args.project:
        cli.set_project(args.project)
    
    # Start chat loop
    cli.chat_loop()
    
    return 0


if __name__ == "__main__":
    sys.exit(main())