import ast
import json
import os
import re
from typing import Any

IGNORED_DIRS = {
    "node_modules",
    "venv",
    ".venv",
    "dist",
    "build",
    ".git",
    "__pycache__",
    ".next",
    "coverage",
    ".pytest_cache",
}
VALID_EXTENSIONS = {".py", ".js", ".ts", ".tsx", ".jsx", ".json"}

JS_BLOCK_START = re.compile(
    r"^(\s*)(export\s+)?(default\s+)?(async\s+)?(function\s+\w+|class\s+\w+)|"
    r"^(\s*)(export\s+)?const\s+\w+\s*=\s*(async\s*)?\(",
    re.MULTILINE,
)


def _should_skip_dir(name: str) -> bool:
    return name in IGNORED_DIRS or name.startswith(".")


def _collect_file_paths(base_path: str) -> list[str]:
    paths: list[str] = []
    for root, dirs, files in os.walk(base_path):
        dirs[:] = [d for d in dirs if not _should_skip_dir(d)]
        for f in files:
            if os.path.splitext(f)[1] in VALID_EXTENSIONS:
                full = os.path.join(root, f)
                rel = os.path.relpath(full, base_path).replace("\\", "/")
                paths.append(rel)
    return sorted(paths)


def _paths_to_tree(rel_paths: list[str]) -> list[dict[str, Any]]:
    root: dict[str, Any] = {}

    for rel in rel_paths:
        parts = rel.split("/")
        node = root
        for i, part in enumerate(parts):
            is_file = i == len(parts) - 1
            if is_file:
                node.setdefault("__files__", []).append(
                    {"name": part, "type": "file", "path": rel}
                )
            else:
                node = node.setdefault(part, {})

    def convert(name: str, subtree: dict[str, Any], prefix: str) -> dict[str, Any]:
        children: list[dict[str, Any]] = []
        for key in sorted(k for k in subtree.keys() if k != "__files__"):
            child_prefix = f"{prefix}/{key}" if prefix else key
            children.append(convert(key, subtree[key], child_prefix))
        for f in sorted(subtree.get("__files__", []), key=lambda x: x["name"]):
            children.append(f)
        return {
            "name": name,
            "type": "folder",
            "path": prefix,
            "children": children,
        }

    top_children: list[dict[str, Any]] = []
    for key in sorted(k for k in root.keys() if k != "__files__"):
        top_children.append(convert(key, root[key], key))
    for f in sorted(root.get("__files__", []), key=lambda x: x["name"]):
        top_children.append(f)
    return top_children


def _chunk_python(filepath: str, content: str) -> list[dict[str, Any]]:
    chunks: list[dict[str, Any]] = []
    try:
        tree = ast.parse(content)
    except SyntaxError:
        return _chunk_fallback_lines(filepath, content)

    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            seg = ast.get_source_segment(content, node)
            if not seg:
                continue
            start = getattr(node, "lineno", 1)
            end = getattr(node, "end_lineno", start + seg.count("\n"))
            chunks.append(
                {
                    "filepath": filepath,
                    "content": seg.strip(),
                    "start_line": start,
                    "end_line": end,
                    "kind": type(node).__name__,
                    "symbol": node.name,
                }
            )

    if not chunks:
        return _chunk_fallback_lines(filepath, content)
    return chunks


def _chunk_javascript_like(filepath: str, content: str) -> list[dict[str, Any]]:
    lines = content.splitlines()
    indices: list[int] = [0]
    for m in JS_BLOCK_START.finditer(content):
        line_no = content[: m.start()].count("\n")
        if line_no > indices[-1]:
            indices.append(line_no)

    indices = sorted(set(indices))
    chunks: list[dict[str, Any]] = []
    for i, start_line in enumerate(indices):
        end_line = indices[i + 1] if i + 1 < len(indices) else len(lines)
        block = "\n".join(lines[start_line:end_line])
        if block.strip():
            chunks.append(
                {
                    "filepath": filepath,
                    "content": block.strip(),
                    "start_line": start_line + 1,
                    "end_line": end_line,
                    "kind": "block",
                    "symbol": "",
                }
            )

    if not chunks:
        return _chunk_fallback_lines(filepath, content)
    return chunks


def _chunk_json(filepath: str, content: str) -> list[dict[str, Any]]:
    max_lines = 120
    lines = content.splitlines()
    chunks: list[dict[str, Any]] = []
    for i in range(0, len(lines), max_lines):
        block = "\n".join(lines[i : i + max_lines])
        if block.strip():
            chunks.append(
                {
                    "filepath": filepath,
                    "content": block.strip(),
                    "start_line": i + 1,
                    "end_line": min(i + max_lines, len(lines)),
                    "kind": "json",
                    "symbol": "",
                }
            )
    return chunks or _chunk_fallback_lines(filepath, content)


def _chunk_fallback_lines(filepath: str, content: str, size: int = 60) -> list[dict[str, Any]]:
    lines = content.splitlines()
    chunks: list[dict[str, Any]] = []
    for i in range(0, len(lines), size):
        block = "\n".join(lines[i : i + size])
        if block.strip():
            chunks.append(
                {
                    "filepath": filepath,
                    "content": block.strip(),
                    "start_line": i + 1,
                    "end_line": min(i + size, len(lines)),
                    "kind": "lines",
                    "symbol": "",
                }
            )
    return chunks


def _chunk_file(filepath: str, full_path: str) -> list[dict[str, Any]]:
    try:
        with open(full_path, "r", encoding="utf-8") as f:
            content = f.read()
    except (OSError, UnicodeDecodeError):
        return []

    ext = os.path.splitext(filepath)[1].lower()
    if ext == ".py":
        return _chunk_python(filepath, content)
    if ext in (".js", ".ts", ".tsx", ".jsx"):
        return _chunk_javascript_like(filepath, content)
    if ext == ".json":
        try:
            json.loads(content)
        except json.JSONDecodeError:
            return _chunk_fallback_lines(filepath, content)
        return _chunk_json(filepath, content)
    return _chunk_fallback_lines(filepath, content)


def resolve_repo_root(extract_dir: str) -> str:
    try:
        entries = [e for e in os.listdir(extract_dir) if not e.startswith(".")]
    except OSError:
        return extract_dir
    if len(entries) == 1:
        sole = os.path.join(extract_dir, entries[0])
        if os.path.isdir(sole):
            return sole
    return extract_dir


def process_directory(base_path: str) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    rel_paths = _collect_file_paths(base_path)
    structure = _paths_to_tree(rel_paths)

    chunks: list[dict[str, Any]] = []
    for rel in rel_paths:
        full = os.path.join(base_path, rel.replace("/", os.sep))
        chunks.extend(_chunk_file(rel, full))

    return chunks, structure
