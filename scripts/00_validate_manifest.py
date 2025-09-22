import sys, os, yaml
from pathlib import Path
from rich import print

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "warehouse" / "manifest.yaml"

def main():
    if not MANIFEST.exists():
        print(f"[red]Missing manifest:[/red] {MANIFEST}")
        sys.exit(1)
    data = yaml.safe_load(MANIFEST.read_text(encoding="utf-8"))
    projects = data.get("projects", [])
    if not projects:
        print("[red]No 'projects' in manifest.[/red]")
        sys.exit(1)

    ok = True
    print("[bold]Validating manifest projects:[/bold]")
    for p in projects:
        name = p.get("name")
        root_path = p.get("root_path")  # Fixed: was "root"
        include = p.get("include", [])
        exclude = p.get("exclude", [])
        if not name or not root_path:
            print(f"[red]- Bad entry (missing name/root_path):[/red] {p}")
            ok = False
            continue
        path_obj = Path(root_path)
        exists = path_obj.exists()
        print(f"• {name}: root_path=[cyan]{root_path}[/cyan]  exists={exists}")
        if not exists:
            ok = False
        if not include:
            print("  [yellow]- Warning:[/yellow] empty 'include' list")
        # Just echo excludes to confirm
        if exclude:
            print(f"  - exclude globs: {exclude}")

    if not ok:
        print("[red]One or more project roots do not exist. Fix paths and re-run.[/red]")
        sys.exit(2)
    print("[green]Manifest validation OK.[/green]")

if __name__ == "__main__":
    main()
