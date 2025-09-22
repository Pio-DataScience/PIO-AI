# scripts/22_where_is_line.py

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import argparse, yaml
from pathlib import Path
from rich import print
from services.indexer.ast_index import where_is_line

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "warehouse" / "manifest.yaml"
INDEX_DIR = ROOT / "indexes" / "symbols"

def sanitize(name: str) -> str:
    return "".join(ch if ch.isalnum() or ch in ("-", "_") else "_" for ch in name)

def main():
    ap = argparse.ArgumentParser(description="Find enclosing node for a path:line")
    ap.add_argument("--project", required=True, help="Project name as in manifest (e.g., AI_AML)")
    ap.add_argument("--path", required=True, help="Relative POSIX path under project root (e.g., src/utils/system_monitoring/path_resolver.py)")
    ap.add_argument("--line", required=True, type=int, help="1-based line number")
    args = ap.parse_args()

    data = yaml.safe_load(MANIFEST.read_text(encoding="utf-8"))
    project = next((p for p in data["projects"] if p["name"] == args.project), None)
    if not project:
        print(f"[red]Project not found in manifest:[/red] {args.project}")
        sys.exit(1)

    db_path = INDEX_DIR / f"{sanitize(args.project)}.sqlite"
    if not db_path.exists():
        print(f"[red]Index not found:[/red] {db_path}\nBuild it first with scripts/21_build_ast_index.py")
        sys.exit(1)

    # Path must be POSIX relative (same as stored)
    rel_posix = args.path.replace("\\", "/")
    rec = where_is_line(db_path, rel_posix, args.line)
    if not rec:
        print("[yellow]No node found for that path:line.[/yellow]")
        sys.exit(2)

    print(f"[bold]{rec['kind']}[/bold] {rec['qualname']}  "
          f"[dim]{rec['start_line']}–{rec['end_line']}[/dim]")

if __name__ == "__main__":
    main()
