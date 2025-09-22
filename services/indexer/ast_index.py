# services/indexer/ast_index.py
from __future__ import annotations
import ast
import hashlib
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List, Optional, Tuple
from fnmatch import fnmatch

# ---------- File expansion (respects manifest includes/excludes) ----------

def _is_dir_excluded(rel_parts: List[str], banned_dirs: set[str]) -> bool:
    return any(p in banned_dirs for p in rel_parts)

def _expand_files(root: Path, includes: Iterable[str], excludes: Iterable[str]) -> List[Path]:
    """
    Expand files under `root` that match `includes` and NOT `excludes`.
    - Directory-style excludes are normalized into segment bans for reliability.
    - File glob excludes (e.g., *.csv) are applied after include.
    """
    # infer banned dir segments from common patterns in excludes
    banned_dirs = {
        ".git", ".venv", "__pycache__", "node_modules",
        "dist", "build", "logs", "data", "checkpoints",
        "models", "notebooks", ".gitbook"
    }
    extra_file_globs: List[str] = []
    for ex in excludes or []:
        ex_norm = ex.strip().strip("/")
        # crude mapping: if it ends with a bare segment, treat as dir
        if ex_norm in banned_dirs:
            continue
        if "/.git/" in ex or ex_norm.endswith(".git"):
            banned_dirs.add(".git")
        elif any(seg in ex_norm for seg in ["__pycache__", ".venv", "node_modules", "dist", "build", "logs", "data", "checkpoints", "models", "notebooks", ".gitbook"]):
            banned_dirs.add(ex_norm.split("/")[-1])
        else:
            extra_file_globs.append(ex)

    files = []
    patterns = list(includes or ["**/*"])
    for p in root.rglob("*"):
        if not p.is_file():
            continue
        rel_posix = p.relative_to(root).as_posix()
        rel_parts = rel_posix.split("/")

        # exclude whole dir segments early
        if _is_dir_excluded(rel_parts, banned_dirs):
            continue
        # include filter
        if not any(fnmatch(rel_posix, pat) for pat in patterns):
            continue
        # file-level excludes
        if any(fnmatch(rel_posix, pat) for pat in extra_file_globs):
            continue

        files.append(p)

    # Only Python source for AST (skip .pyc, etc.)
    files = [f for f in files if f.suffix.lower() == ".py"]
    return sorted(files)

# ---------- AST parsing & node extraction ----------

@dataclass
class NodeRec:
    path: str              # POSIX relative path
    kind: str              # Module | Class | Function | AsyncFunction
    name: str              # simple name or "<module>"
    qualname: str          # dotted path, e.g., pkg.mod.Class.method
    start_line: int
    end_line: int
    parent_qualname: Optional[str]
    docstring: Optional[str]

def _hash_bytes(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()

def _read_text_safe(p: Path) -> str:
    # Be lenient with encodings (Arabic, etc.)
    return p.read_text(encoding="utf-8", errors="ignore")

def _iter_nodes(src: str, rel_path: str) -> Tuple[List[NodeRec], Optional[str]]:
    """
    Walk the AST, collecting module/class/function nodes with line ranges and docstrings.
    Returns (nodes, module_docstring)
    """
    tree = ast.parse(src, filename=rel_path)
    module_doc = ast.get_docstring(tree)
    stack: List[str] = []  # for qualname buildup
    out: List[NodeRec] = []

    def push(name: str): stack.append(name)
    def pop(): stack.pop()

    def add_node(kind: str, name: str, node: ast.AST, parent_qn: Optional[str], doc: Optional[str]):
        start = getattr(node, "lineno", 1)
        end = getattr(node, "end_lineno", start)
        qual = ".".join([*stack, name]) if name != "<module>" else rel_path.replace("/", ".")
        out.append(NodeRec(
            path=rel_path, kind=kind, name=name, qualname=qual,
            start_line=start, end_line=end, parent_qualname=parent_qn, docstring=doc
        ))

    # Add a synthetic module node spanning whole file
    # We approximate end_line by counting lines
    total_lines = len(src.splitlines()) or 1
    add_node("Module", "<module>", tree, None, module_doc)
    out[-1].end_line = total_lines

    class V(ast.NodeVisitor):
        def visit_ClassDef(self, node: ast.ClassDef):
            parent_qn = ".".join(stack) if stack else None
            doc = ast.get_docstring(node)
            name = node.name
            add_node("Class", name, node, parent_qn, doc)
            push(name); self.generic_visit(node); pop()

        def visit_FunctionDef(self, node: ast.FunctionDef):
            parent_qn = ".".join(stack) if stack else None
            doc = ast.get_docstring(node)
            name = node.name
            add_node("Function", name, node, parent_qn, doc)
            push(name); self.generic_visit(node); pop()

        def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef):
            parent_qn = ".".join(stack) if stack else None
            doc = ast.get_docstring(node)
            name = node.name
            add_node("AsyncFunction", name, node, parent_qn, doc)
            push(name); self.generic_visit(node); pop()

    V().visit(tree)
    return out, module_doc

# ---------- SQLite schema & writer ----------

SCHEMA_SQL = """
PRAGMA journal_mode=WAL;
PRAGMA synchronous=NORMAL;

CREATE TABLE IF NOT EXISTS files(
  path TEXT PRIMARY KEY,       -- POSIX relative path
  mtime REAL NOT NULL,
  sha256 TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS nodes(
  id INTEGER PRIMARY KEY,
  path TEXT NOT NULL,          -- POSIX relative path
  kind TEXT NOT NULL,          -- Module | Class | Function | AsyncFunction
  name TEXT NOT NULL,          -- simple name or "<module>"
  qualname TEXT NOT NULL,      -- dotted qualname
  parent_qualname TEXT,        -- qualname of parent (class/function/module)
  start_line INTEGER NOT NULL,
  end_line INTEGER NOT NULL,
  docstring TEXT
);

CREATE INDEX IF NOT EXISTS idx_nodes_path_lines ON nodes(path, start_line, end_line);
CREATE INDEX IF NOT EXISTS idx_nodes_qualname ON nodes(qualname);
CREATE INDEX IF NOT EXISTS idx_nodes_kind ON nodes(kind);
"""

def _ensure_db(db_path: Path) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(str(db_path))
    con.executescript(SCHEMA_SQL)
    return con

def _to_posix(root: Path, p: Path) -> str:
    return p.relative_to(root).as_posix()

def build_project_ast_index(
    project_name: str,
    root: Path,
    includes: Iterable[str],
    excludes: Iterable[str],
    out_db: Path
) -> dict:
    """
    Build/update AST symbol index for a single project.
    Returns stats: {"files": N, "nodes": M, "db": "path"}
    """
    files = _expand_files(root, includes, excludes)
    con = _ensure_db(out_db)
    cur = con.cursor()

    # wipe and rebuild for simplicity (small projects); optimize later if needed
    cur.execute("DELETE FROM files;")
    cur.execute("DELETE FROM nodes;")
    con.commit()

    total_nodes = 0
    for f in files:
        rel = _to_posix(root, f)
        try:
            txt = _read_text_safe(f)
        except Exception as e:
            # skip unreadable files
            continue

        try:
            nodes, _ = _iter_nodes(txt, rel)
        except SyntaxError:
            # keep file row so we know it was skipped
            nodes = []

        sha = _hash_bytes(txt.encode("utf-8", errors="ignore"))
        mtime = f.stat().st_mtime

        cur.execute("INSERT OR REPLACE INTO files(path, mtime, sha256) VALUES (?,?,?)",
                    (rel, mtime, sha))

        if nodes:
            cur.executemany(
                """INSERT INTO nodes(path, kind, name, qualname, parent_qualname, start_line, end_line, docstring)
                   VALUES (?,?,?,?,?,?,?,?)""",
                [(n.path, n.kind, n.name, n.qualname, n.parent_qualname, n.start_line, n.end_line, n.docstring)
                 for n in nodes]
            )
            total_nodes += len(nodes)

    con.commit()
    con.close()
    return {"files": len(files), "nodes": total_nodes, "db": str(out_db)}

# ---------- Query helper (used by tester script) ----------

def where_is_line(db_path: Path, rel_posix_path: str, line: int) -> Optional[dict]:
    """
    Return the *smallest* node enclosing (path, line), or None.
    """
    con = sqlite3.connect(str(db_path))
    cur = con.cursor()
    cur.execute(
        """SELECT kind, name, qualname, parent_qualname, start_line, end_line
           FROM nodes
           WHERE path = ? AND start_line <= ? AND end_line >= ?
           ORDER BY (end_line - start_line) ASC
           LIMIT 1""",
        (rel_posix_path, line, line)
    )
    row = cur.fetchone()
    con.close()
    if not row:
        return None
    kind, name, qualname, parent, s, e = row
    return {
        "kind": kind, "name": name, "qualname": qualname,
        "parent_qualname": parent, "start_line": s, "end_line": e
    }
