#!/usr/bin/env python3
"""
Bundle a React app into LLM-friendly markdown.

Examples:
  python bundle_react_for_llm.py /path/to/app --out bundle.md
  python bundle_react_for_llm.py . --chunk --chunk-bytes 900000
"""

from __future__ import annotations

import argparse
import fnmatch
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List, Optional, Tuple

# ---- Defaults ----

DEFAULT_EXCLUDE_DIRS = {
    ".git",
    "node_modules",
    "dist",
    "build",
    ".next",
    ".turbo",
    ".cache",
    "coverage",
    ".vite",
    ".parcel-cache",
    ".storybook-static",
    ".idea",
    ".vscode",
}

DEFAULT_INCLUDE_GLOBS = [
    # source
    "src/**/*",
    "app/**/*",          # some frameworks use /app
    "pages/**/*",        # next.js style
    "components/**/*",
    "hooks/**/*",
    "lib/**/*",
    "utils/**/*",
    "public/**/*",       # optional but often helpful (small)
    # configs
    "package.json",
    "package-lock.json",
    "pnpm-lock.yaml",
    "yarn.lock",
    "tsconfig.json",
    "tsconfig.*.json",
    "jsconfig.json",
    "vite.config.*",
    "webpack.config.*",
    "craco.config.*",
    "next.config.*",
    "eslint.config.*",
    ".eslintrc*",
    ".prettierrc*",
    "prettier.config.*",
    "postcss.config.*",
    "tailwind.config.*",
    "babel.config.*",
    ".babelrc*",
    "jest.config.*",
    "vitest.config.*",
    "cypress.config.*",
    "playwright.config.*",
    ".env.example",
    "README*",
    "CONTRIBUTING*",
    "LICENSE*",
]

# Include only text-ish extensions by default
DEFAULT_TEXT_EXTS = {
    ".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs",
    ".css", ".scss", ".sass", ".less",
    ".html", ".md", ".mdx", ".txt",
    ".json", ".yaml", ".yml",
    ".env", ".example", ".toml",
    ".graphql", ".gql",
    ".svg",  # often small and sometimes relevant (icons)
}

DEFAULT_EXCLUDE_GLOBS = [
    "**/*.min.js",
    "**/*.min.css",
    "**/*.map",
    "**/generated/**",
    "**/*.generated.*",
    "**/*.lockb",
]

@dataclass
class FileEntry:
    rel: str
    abs: Path
    size: int

def is_under_excluded_dir(path: Path, root: Path, exclude_dirs: set[str]) -> bool:
    try:
        rel_parts = path.relative_to(root).parts
    except ValueError:
        return True
    return any(part in exclude_dirs for part in rel_parts)

def matches_any_glob(rel_posix: str, globs: Iterable[str]) -> bool:
    for g in globs:
        # fnmatch uses Unix-style patterns when rel is posix
        if fnmatch.fnmatch(rel_posix, g):
            return True
        # Also allow patterns like src/**/* by approximating with fnmatch
        # (fnmatch treats ** just like *; good enough for our use)
    return False

def collect_files(
    root: Path,
    include_globs: List[str],
    exclude_dirs: set[str],
    exclude_globs: List[str],
    text_exts: set[str],
    max_file_bytes: int,
) -> List[FileEntry]:
    root = root.resolve()
    out: List[FileEntry] = []

    for p in root.rglob("*"):
        if not p.is_file():
            continue

        if is_under_excluded_dir(p, root, exclude_dirs):
            continue

        rel = p.relative_to(root).as_posix()

        # Exclude by glob first
        if matches_any_glob(rel, exclude_globs):
            continue

        # Include by glob (or by extension if not matched but config file)
        included = matches_any_glob(rel, include_globs)
        ext = p.suffix.lower()

        # Always include some important root files even if glob misses
        root_file_allow = ("/" not in rel) and matches_any_glob(rel, include_globs)

        if not (included or root_file_allow):
            # fallback: include if extension is in text_exts and file is inside src-ish folders
            if ext in text_exts and (rel.startswith("src/") or rel.startswith("app/") or rel.startswith("pages/")):
                included = True

        if not included:
            continue

        try:
            size = p.stat().st_size
        except OSError:
            continue

        # Skip huge binary-ish files (we'll also guard by extension)
        if ext and ext not in text_exts and not matches_any_glob(rel, include_globs):
            continue

        # Keep, but we'll trim later when writing
        out.append(FileEntry(rel=rel, abs=p, size=size))

    out.sort(key=lambda e: e.rel)
    # Optional: drop files that are *massive* (likely vendor bundles)
    out = [e for e in out if e.size <= max_file_bytes or Path(e.rel).suffix.lower() in text_exts]
    return out

def read_text_lossy(path: Path, max_bytes: int) -> Tuple[str, bool]:
    """
    Reads up to max_bytes from file. Returns (text, truncated?).
    """
    data = path.read_bytes()
    truncated = False
    if len(data) > max_bytes:
        data = data[:max_bytes]
        truncated = True
    # decode lossy
    text = data.decode("utf-8", errors="replace")
    return text, truncated

def render_bundle(entries: List[FileEntry], root: Path, per_file_max_bytes: int) -> str:
    lines: List[str] = []
    lines.append("# React App Bundle for LLM Analysis")
    lines.append("")
    lines.append(f"- Root: `{root.resolve()}`")
    lines.append(f"- Files included: **{len(entries)}**")
    lines.append(f"- Per-file max bytes: **{per_file_max_bytes}**")
    lines.append("")
    lines.append("## File Index")
    lines.append("")
    for i, e in enumerate(entries, 1):
        lines.append(f"{i}. `{e.rel}` ({e.size} bytes)")
    lines.append("")
    lines.append("## Files")
    lines.append("")

    for e in entries:
        p = e.abs
        ext = p.suffix.lower()
        fence = "tsx" if ext == ".tsx" else ("ts" if ext == ".ts" else ("jsx" if ext == ".jsx" else ("js" if ext in {".js", ".mjs", ".cjs"} else "")))
        content, truncated = read_text_lossy(p, per_file_max_bytes)
        lines.append(f"### `{e.rel}`")
        if truncated:
            lines.append(f"> ⚠️ Truncated to first {per_file_max_bytes} bytes.")
        lines.append("")
        lines.append(f"```{fence}".rstrip())
        lines.append(content.rstrip("\n"))
        lines.append("```")
        lines.append("")

    return "\n".join(lines)

def write_chunked(text: str, out_path: Path, chunk_bytes: int) -> List[Path]:
    out_paths: List[Path] = []
    b = text.encode("utf-8")
    total = len(b)
    if total <= chunk_bytes:
        out_path.write_text(text, encoding="utf-8")
        return [out_path]

    stem = out_path.stem
    suffix = out_path.suffix or ".md"
    parent = out_path.parent
    parent.mkdir(parents=True, exist_ok=True)

    idx = 1
    start = 0
    while start < total:
        end = min(start + chunk_bytes, total)
        # ensure we cut on a newline boundary if possible
        cut = b.rfind(b"\n", start, end)
        if cut != -1 and cut > start + 1000:
            end = cut + 1

        part = b[start:end].decode("utf-8", errors="replace")
        part_path = parent / f"{stem}_part_{idx:03d}{suffix}"
        part_path.write_text(part, encoding="utf-8")
        out_paths.append(part_path)

        start = end
        idx += 1

    return out_paths

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("root", nargs="?", default=".", help="Repo root (default: .)")
    ap.add_argument("--out", default="bundle.md", help="Output filename (default: bundle.md)")
    ap.add_argument("--per-file-bytes", type=int, default=200_000, help="Max bytes per file included (default: 200k)")
    ap.add_argument("--max-file-bytes", type=int, default=3_000_000, help="Skip extremely large files (default: 3MB)")
    ap.add_argument("--chunk", action="store_true", help="Split output into multiple files")
    ap.add_argument("--chunk-bytes", type=int, default=900_000, help="Chunk size in bytes (default: 900k)")
    ap.add_argument("--include", action="append", default=[], help="Additional include glob (repeatable)")
    ap.add_argument("--exclude", action="append", default=[], help="Additional exclude glob (repeatable)")
    ap.add_argument("--no-public", action="store_true", help="Exclude public/ from default include globs")
    args = ap.parse_args()

    root = Path(args.root).resolve()
    out_path = Path(args.out).resolve()

    include_globs = list(DEFAULT_INCLUDE_GLOBS)
    if args.no_public:
        include_globs = [g for g in include_globs if not g.startswith("public/")]
    include_globs.extend(args.include)

    exclude_globs = list(DEFAULT_EXCLUDE_GLOBS)
    exclude_globs.extend(args.exclude)

    entries = collect_files(
        root=root,
        include_globs=include_globs,
        exclude_dirs=set(DEFAULT_EXCLUDE_DIRS),
        exclude_globs=exclude_globs,
        text_exts=set(DEFAULT_TEXT_EXTS),
        max_file_bytes=args.max_file_bytes,
    )

    bundle = render_bundle(entries, root=root, per_file_max_bytes=args.per_file_bytes)

    if args.chunk:
        parts = write_chunked(bundle, out_path, args.chunk_bytes)
        print("Wrote:")
        for p in parts:
            print(" -", p)
    else:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(bundle, encoding="utf-8")
        print("Wrote:", out_path)

if __name__ == "__main__":
    main()
