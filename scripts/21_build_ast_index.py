# scripts/21_build_ast_index.py
from pathlib import Path
import sys
import os

# Add the parent directory (PIO-AI root) to Python path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import yaml
from rich import print
from services.indexer.ast_index import build_project_ast_index
MANIFEST = ROOT / "warehouse" / "manifest.yaml"
INDEX_DIR = ROOT / "indexes" / "symbols"


def sanitize(name: str) -> str:
    return "".join(ch if ch.isalnum() or ch in ("-", "_") else "_" for ch in name)

def main():
    if not MANIFEST.exists():
        print(f"[red]Missing manifest:[/red] {MANIFEST}"); sys.exit(1)
    data = yaml.safe_load(MANIFEST.read_text(encoding="utf-8"))
    projects = data.get("projects", [])
    if not projects:
        print("[red]No projects in manifest.[/red]"); sys.exit(1)

    INDEX_DIR.mkdir(parents=True, exist_ok=True)
    totals_files = 0
    totals_nodes = 0

    for proj in projects:
        name = proj["name"]
        root = Path(proj["root_path"])
        includes = proj.get("include", ["**/*.py"])
        excludes = proj.get("exclude", [])
        if not root.exists():
            print(f"[yellow]Skip {name}[/yellow]: root missing {root}")
            continue
        db_path = INDEX_DIR / f"{sanitize(name)}.sqlite"
        stats = build_project_ast_index(name, root, includes, excludes, db_path)
        totals_files += stats["files"]
        totals_nodes += stats["nodes"]
        print(f"[bold]{name}[/bold] → {stats['files']} py files, {stats['nodes']} nodes  [dim]{db_path}[/dim]")

    print(f"\n[green]Done.[/green] Indexed files: {totals_files}, nodes: {totals_nodes}")

if __name__ == "__main__":
    main()
