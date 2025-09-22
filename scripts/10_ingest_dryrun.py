import sys, yaml
from pathlib import Path
from rich import print
from fnmatch import fnmatch

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "warehouse" / "manifest.yaml"
# Segment-based directory excludes for reliability
DEFAULT_BANNED_DIRS = {
    ".git", ".venv", "__pycache__", "node_modules",
    "dist", "build", "logs", "data", "checkpoints",
    "models", "notebooks",
}

def is_banned_dir(rel_parts, extra_banned_dirs):
    banned = DEFAULT_BANNED_DIRS | set(extra_banned_dirs or [])
    return any(part in banned for part in rel_parts)

def is_banned_file(rel_posix, exclude_globs):
    # honor explicit file globs like '*.parquet', '*.csv', or 'foo/**'
    return any(fnmatch(rel_posix, pat) for pat in (exclude_globs or []))

def iter_included_files(root: Path, includes, excludes):
    # Turn any directory-style excludes like '**/.git/**' into segment names we can drop early
    extra_banned_dirs = []
    extra_file_globs  = []

    for ex in excludes or []:
        # crude heuristic: if pattern mentions '/.something/' or a bare segment, treat as a dir
        if "/.git/" in ex or ex.strip("/").endswith(".git") or ex.strip("/").startswith(".git"):
            extra_banned_dirs.append(".git")
        elif any(seg in ex for seg in ["/.venv/", "/__pycache__/", "/node_modules/", "/dist/", "/build/",
                                       "/logs/", "/data/", "/checkpoints/", "/models/", "/notebooks/"]):
            # collect the last segment that looks like a dir name
            extra_banned_dirs.append(ex.strip("/").split("/")[-1])
        else:
            extra_file_globs.append(ex)

    files = []
    # Expand includes by scanning once and matching globs
    for p in root.rglob("*"):
        if not p.is_file():
            continue
        rel_posix = p.relative_to(root).as_posix()
        rel_parts = rel_posix.split("/")

        # directory ban first (fast and reliable)
        if is_banned_dir(rel_parts, extra_banned_dirs):
            continue

        # include filter
        if includes:
            if not any(fnmatch(rel_posix, inc) for inc in includes):
                continue
        # file-level exclude (globs)
        if is_banned_file(rel_posix, extra_file_globs):
            continue

        files.append(p)

    return sorted(files)

def main():
    if not MANIFEST.exists():
        print(f"[red]Missing manifest:[/red] {MANIFEST}"); sys.exit(1)
    data = yaml.safe_load(MANIFEST.read_text(encoding="utf-8"))
    projects = data.get("projects", [])
    if not projects:
        print("[red]No 'projects' in manifest.[/red]"); sys.exit(1)

    total_files = 0
    for proj in projects:
        name = proj["name"]
        root = Path(proj["root_path"])  # Fixed: was "root"
        includes = proj.get("include", ["**/*"])
        excludes = proj.get("exclude", [])

        if not root.exists():
            print(f"[red]Skip {name}[/red]: root_path missing {root}")
            continue

        files = iter_included_files(root, includes, excludes)
        total_files += len(files)

        print(f"[bold cyan]{name}[/bold cyan] — root: {root}")
        print(f"  matched files: [green]{len(files)}[/green]")
        # show samples from head/tail
        samples = (files[:5] + files[-5:]) if len(files) > 10 else files
        for sample in samples:
            rel = sample.relative_to(root).as_posix()
            print(f"   • {rel}")
        print()

    print(f"[bold]TOTAL matched files across projects:[/bold] {total_files}")
    print("[dim]Dry-run complete.[/dim]")

if __name__ == "__main__":
    main()
