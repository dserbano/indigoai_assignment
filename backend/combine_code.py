#!/usr/bin/env python3
"""
combine_code.py

Bundle a FastAPI (or any Python) codebase into a single TXT file for LLMs.

Examples:
  python combine_code.py
  python combine_code.py --root . --out fastapi_bundle.txt
  python combine_code.py --include "app/**" "src/**" --include-ext .py .toml .md
  python combine_code.py --exclude "tests/**" "**/__pycache__/**" --max-bytes 2000000
  python combine_code.py --tree --line-numbers
"""

from __future__ import annotations

import argparse
import fnmatch
import os
from pathlib import Path
from typing import Iterable, List, Optional, Tuple


DEFAULT_EXCLUDE_GLOBS = [
    # VCS / tooling
    ".git/**",
    ".hg/**",
    ".svn/**",
    ".idea/**",
    ".vscode/**",
    ".ruff_cache/**",
    ".mypy_cache/**",
    ".pytest_cache/**",
    ".tox/**",
    ".venv/**",
    "venv/**",
    "env/**",
    "dist/**",
    "build/**",
    "*.egg-info/**",
    ".DS_Store",
    # Python noise
    "**/__pycache__/**",
    "**/*.pyc",
    "**/*.pyo",
    # Node noise (often present in fullstack repos)
    "node_modules/**",
    # Logs / data / binaries
    "**/*.log",
    "**/*.sqlite",
    "**/*.db",
    "**/*.png",
    "**/*.jpg",
    "**/*.jpeg",
    "**/*.gif",
    "**/*.webp",
    "**/*.pdf",
    "**/*.zip",
    "**/*.tar",
    "**/*.gz",
    "**/*.7z",
]

DEFAULT_INCLUDE_EXT = [
    ".py",
    ".pyi",
    ".toml",
    ".ini",
    ".cfg",
    ".yaml",
    ".yml",
    ".json",
    ".md",
    ".txt",
    ".env",          # careful: may contain secrets; you can exclude it
    ".dockerfile",   # rare
    "Dockerfile",    # special-case by name below
    "Makefile",      # special-case by name below
]


def normalize_glob(g: str) -> str:
    # Make globs consistent on Windows too.
    return g.replace("\\", "/")


def rel_posix(path: Path, root: Path) -> str:
    return normalize_glob(str(path.relative_to(root)))


def matches_any(path_posix: str, globs: Iterable[str]) -> bool:
    for g in globs:
        if fnmatch.fnmatch(path_posix, normalize_glob(g)):
            return True
    return False


def is_text_file(p: Path) -> bool:
    # Quick heuristic: try decoding a small chunk as utf-8.
    try:
        with p.open("rb") as f:
            chunk = f.read(4096)
        chunk.decode("utf-8")
        return True
    except Exception:
        return False


def should_include_file(
    p: Path,
    root: Path,
    include_globs: List[str],
    exclude_globs: List[str],
    include_ext: List[str],
) -> bool:
    rp = rel_posix(p, root)

    if matches_any(rp, exclude_globs):
        return False

    # If include globs provided, file must match at least one
    if include_globs and not matches_any(rp, include_globs):
        return False

    name = p.name

    # Special-case common config files by exact name
    if name in ("Dockerfile", "Makefile"):
        return True

    # Special-case .env and similar dotfiles by suffix or exact match
    if name.startswith(".") and name in (".env", ".env.example", ".env.template"):
        return True

    # Extension-based include
    suffix = p.suffix.lower()
    if suffix in [e.lower() for e in include_ext if e.startswith(".")]:
        return True

    return False


def iter_files(root: Path) -> Iterable[Path]:
    for dirpath, dirnames, filenames in os.walk(root):
        # Prevent descending into excluded directories early if possible (basic)
        # We'll still filter on full relative path later.
        for fname in filenames:
            yield Path(dirpath) / fname


def build_tree(paths: List[Path], root: Path) -> str:
    # Build a simple file tree from included paths only.
    rels = sorted(rel_posix(p, root) for p in paths)
    lines: List[str] = []
    for r in rels:
        parts = r.split("/")
        indent = 0
        # Print each path as a single indented line
        # (avoids huge tree logic; still readable)
        lines.append("  " * indent + r)
    return "\n".join(lines)


def read_file_text(p: Path, max_bytes: Optional[int]) -> Tuple[str, int]:
    data = p.read_bytes()
    if max_bytes is not None and len(data) > max_bytes:
        data = data[:max_bytes]
        truncated = 1
    else:
        truncated = 0

    # decode with replacement to avoid hard failures
    text = data.decode("utf-8", errors="replace")
    return text, truncated


def add_line_numbers(text: str) -> str:
    lines = text.splitlines()
    width = len(str(len(lines))) if lines else 1
    numbered = [f"{str(i+1).rjust(width)} | {line}" for i, line in enumerate(lines)]
    return "\n".join(numbered) + ("\n" if text.endswith("\n") else "")


def main() -> int:
    ap = argparse.ArgumentParser(description="Bundle FastAPI code into one TXT for LLMs.")
    ap.add_argument("--root", default=".", help="Project root directory (default: .)")
    ap.add_argument("--out", default="fastapi_bundle.txt", help="Output txt file path")
    ap.add_argument(
        "--include",
        nargs="*",
        default=[],
        help='Optional include globs (e.g. "app/**" "src/**"). If omitted, includes by extension/name.',
    )
    ap.add_argument(
        "--exclude",
        nargs="*",
        default=[],
        help='Exclude globs (adds to defaults). e.g. "tests/**" ".env"',
    )
    ap.add_argument(
        "--include-ext",
        nargs="*",
        default=[],
        help="Extra extensions to include (e.g. .sql .graphql). Default already includes common ones.",
    )
    ap.add_argument(
        "--no-default-excludes",
        action="store_true",
        help="Do not use the default exclude globs (not recommended).",
    )
    ap.add_argument(
        "--max-file-bytes",
        type=int,
        default=None,
        help="Max bytes to read per file; larger files will be truncated (default: no limit).",
    )
    ap.add_argument(
        "--max-total-bytes",
        type=int,
        default=8_000_000,
        help="Stop once total output content exceeds this many bytes (default: 8,000,000).",
    )
    ap.add_argument("--tree", action="store_true", help="Include a list of bundled files at top.")
    ap.add_argument("--line-numbers", action="store_true", help="Add line numbers to each file section.")
    ap.add_argument(
        "--respect-gitignore",
        action="store_true",
        help="Basic gitignore support (reads .gitignore and adds its patterns as excludes).",
    )

    args = ap.parse_args()

    root = Path(args.root).resolve()
    out_path = Path(args.out).resolve()

    exclude_globs = [] if args.no_default_excludes else list(DEFAULT_EXCLUDE_GLOBS)
    exclude_globs += args.exclude or []

    include_globs = args.include or []

    include_ext = list(DEFAULT_INCLUDE_EXT)
    include_ext += args.include_ext or []

    # Optional: add .gitignore patterns as excludes (basic, best-effort)
    if args.respect_gitignore:
        gitignore = root / ".gitignore"
        if gitignore.exists():
            try:
                for line in gitignore.read_text(encoding="utf-8", errors="ignore").splitlines():
                    s = line.strip()
                    if not s or s.startswith("#"):
                        continue
                    # very basic: treat as glob
                    # normalize leading slash
                    s = s.lstrip("/")
                    # if directory pattern, add /**
                    if s.endswith("/"):
                        s = s + "**"
                    exclude_globs.append(s)
            except Exception:
                pass

    included_paths: List[Path] = []
    for p in iter_files(root):
        if not p.is_file():
            continue
        # Avoid writing the output into itself if re-running.
        if p.resolve() == out_path:
            continue
        if should_include_file(p, root, include_globs, exclude_globs, include_ext):
            # Skip non-text files to avoid garbage.
            if is_text_file(p):
                included_paths.append(p)

    included_paths.sort(key=lambda x: rel_posix(x, root))

    total_written = 0
    trunc_files = 0

    with out_path.open("w", encoding="utf-8", errors="replace") as out:
        header = [
            "FASTAPI / PROJECT BUNDLE FOR LLM",
            f"Root: {root}",
            f"Files included: {len(included_paths)}",
            "",
        ]
        out.write("\n".join(header))

        if args.tree:
            out.write("FILE LIST (relative paths)\n")
            out.write("-" * 80 + "\n")
            out.write(build_tree(included_paths, root) + "\n\n")

        out.write("BEGIN FILE CONTENTS\n")
        out.write("=" * 80 + "\n\n")

        for p in included_paths:
            relp = rel_posix(p, root)
            out.write(f"--- FILE: {relp} ---\n")
            out.write(f"--- ABSOLUTE: {p.resolve()} ---\n")
            out.write("-" * 80 + "\n")

            try:
                text, truncated = read_file_text(p, args.max_file_bytes)
                if args.line_numbers:
                    text = add_line_numbers(text)
                out.write(text)
                if not text.endswith("\n"):
                    out.write("\n")
                if truncated:
                    trunc_files += 1
                    out.write("\n[TRUNCATED: file exceeded --max-file-bytes]\n")
                out.write("\n" + ("=" * 80) + "\n\n")

                total_written += len(text.encode("utf-8", errors="replace"))
                if args.max_total_bytes is not None and total_written > args.max_total_bytes:
                    out.write("[STOPPED: exceeded --max-total-bytes]\n")
                    break
            except Exception as e:
                out.write(f"[ERROR READING FILE: {e}]\n\n" + ("=" * 80) + "\n\n")

        out.write(
            f"SUMMARY\n"
            f"- Included files: {len(included_paths)}\n"
            f"- Truncated files: {trunc_files}\n"
            f"- Output path: {out_path}\n"
        )

    print(f"Wrote bundle to: {out_path}")
    print(f"Included files: {len(included_paths)} | Truncated: {trunc_files}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
