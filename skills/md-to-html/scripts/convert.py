#!/usr/bin/env python3
"""Unified CLI for md-to-html conversions.

Usage:
    python convert.py <mode> [args...]

Modes:
    multi-page   <docs_dir> <output_dir> [--title T]   Multi-page static site
    single-page  <docs_dir> <output_file> [--title T]  Single self-contained HTML
    puppy-page   <input> <output_file> [--title T]     Puppy Pages-compatible HTML
    index        <manifest.json> <output.html> [--title T]  Searchable card index
    lint         <path> [path ...]                      Lint markdown before converting
"""

import sys
from pathlib import Path

USAGE = """Usage: python convert.py <mode> [args...]

Modes:
  lint          Lint markdown files/directories for conversion issues
  multi-page    Build multi-page static HTML site from a docs directory
  single-page   Build single self-contained HTML from a docs directory
  puppy-page    Build Puppy Pages-compatible HTML from file or directory
  index         Build searchable card-based index from a manifest.json

Examples:
  python convert.py lint docs/
  python convert.py multi-page docs/ _site --title "My Docs"
  python convert.py single-page docs/ docs.html --title "My Docs"
  python convert.py puppy-page README.md readme.html
  python convert.py puppy-page docs/ docs.html --title "My Docs"
  python convert.py index manifest.json index.html --title "Report Index"
"""


def main():
    if len(sys.argv) < 2 or sys.argv[1] in ("-h", "--help"):
        print(USAGE)
        sys.exit(0)

    mode = sys.argv[1]
    # Rewrite sys.argv so sub-module parsers see the right args
    sys.argv = [f"convert.py {mode}"] + sys.argv[2:]

    scripts_dir = Path(__file__).resolve().parent
    sys.path.insert(0, str(scripts_dir))

    if mode == "lint":
        from md_lint import main as lint_main

        lint_main()
    elif mode == "multi-page":
        from build_multi_page import main as mp_main

        mp_main()
    elif mode == "single-page":
        from build_single_page import main as sp_main

        sp_main()
    elif mode == "puppy-page":
        from build_puppy_page import main as pp_main

        pp_main()
    elif mode == "index":
        from build_index import main as idx_main

        idx_main()
    else:
        print(f"Unknown mode: {mode}")
        print(USAGE)
        sys.exit(1)


if __name__ == "__main__":
    main()
