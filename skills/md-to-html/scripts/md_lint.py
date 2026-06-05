#!/usr/bin/env python3
"""Markdown linter to catch issues that produce broken HTML.

Checks for common problems that trip up the converter:
  - Unclosed fenced code blocks
  - Headings without space after #
  - Broken table formatting (inconsistent column counts)
  - Unclosed inline formatting (bold/italic)
  - Blank alt text in images (accessibility)
  - Trailing whitespace in links
  - Missing blank lines before block elements

Returns a list of (line_number, severity, message) tuples.
Severity: 'error' = will produce broken HTML, 'warn' = may look wrong.
"""

import re
import sys
from pathlib import Path


def lint_markdown(text: str, filename: str = "<stdin>") -> list[tuple[int, str, str]]:
    """Lint markdown text. Return list of (line_no, severity, message)."""
    issues: list[tuple[int, str, str]] = []
    lines = text.split("\n")

    in_fence = False
    fence_start = 0

    for i, line in enumerate(lines, 1):
        stripped = line.strip()

        # Track fenced code blocks
        if stripped.startswith("```"):
            if in_fence:
                in_fence = False
            else:
                in_fence = True
                fence_start = i
            continue

        if in_fence:
            continue

        # Heading without space: ##Foo
        if re.match(r"^#{1,6}[^#\s]", line):
            issues.append((i, "error", "Heading missing space after '#'"))

        # Table row column count consistency
        if "|" in line and re.match(r"^\s*\|", stripped):
            cols = len(stripped.strip("|").split("|"))
            if i + 1 <= len(lines):
                next_line = lines[i] if i < len(lines) else ""
                if "|" in next_line and re.match(
                    r"^\s*\|[\s:|-]+\|\s*$", next_line.strip()
                ):
                    sep_cols = len(next_line.strip().strip("|").split("|"))
                    if cols != sep_cols:
                        issues.append(
                            (
                                i,
                                "error",
                                f"Table header has {cols} columns but separator has {sep_cols}",
                            )
                        )

        # Broken link syntax: [text] (url) with space
        if re.search(r"\[[^\]]+\]\s+\([^)]+\)", line):
            issues.append(
                (i, "warn", "Space between link text and URL — link won't render")
            )

        # Image with empty alt text
        if "![]()" in line or re.search(r"!\[\]\([^)]+\)", line):
            issues.append((i, "warn", "Image with empty alt text (accessibility)"))

        # Unclosed bold/italic (heuristic: odd count of ** or * not in code)
        code_stripped = re.sub(r"`[^`]+`", "", line)
        bold_count = len(re.findall(r"\*\*", code_stripped))
        if bold_count % 2 != 0:
            issues.append((i, "warn", "Possible unclosed bold (**) formatting"))

        # Missing blank line before heading
        if re.match(r"^#{1,6}\s", line) and i > 1:
            prev = lines[i - 2]  # 0-indexed
            if (
                prev.strip()
                and not prev.strip().startswith("#")
                and not prev.strip().startswith("```")
            ):
                issues.append(
                    (
                        i,
                        "warn",
                        "No blank line before heading — may merge with paragraph",
                    )
                )

        # Missing blank line before list
        if re.match(r"^\s*[-*+]\s", line) and i > 1:
            prev = lines[i - 2]
            if (
                prev.strip()
                and not re.match(r"^\s*[-*+]\s", prev)
                and not prev.strip().startswith(">")
            ):
                issues.append(
                    (i, "warn", "No blank line before list — may merge with paragraph")
                )

    # Unclosed fence at EOF
    if in_fence:
        issues.append((fence_start, "error", "Unclosed fenced code block"))

    return issues


def lint_file(path: Path) -> list[tuple[int, str, str]]:
    """Lint a single markdown file."""
    return lint_markdown(path.read_text(encoding="utf-8"), str(path))


def lint_directory(directory: Path) -> dict[str, list[tuple[int, str, str]]]:
    """Lint all .md files in a directory. Return {filepath: issues}."""
    results: dict[str, list[tuple[int, str, str]]] = {}
    for md in sorted(directory.rglob("*.md")):
        # Skip underscore-prefixed working/authoring files (e.g. _Manifest.md,
        # _DiataxisGuide.md, _UpdateQueue.md, _AuditLog.md) — they are not
        # published pages.
        if md.name.startswith("_"):
            continue
        issues = lint_file(md)
        if issues:
            results[str(md.relative_to(directory))] = issues
    return results


def print_results(results: dict[str, list[tuple[int, str, str]]]) -> int:
    """Print lint results. Return count of errors."""
    errors = 0
    for filepath, issues in results.items():
        for line_no, severity, msg in issues:
            icon = "❌" if severity == "error" else "⚠️"
            print(f"  {icon} {filepath}:{line_no} [{severity}] {msg}")
            if severity == "error":
                errors += 1
    return errors


def main():
    """CLI: lint markdown files or directories."""
    if len(sys.argv) < 2:
        print("Usage: md_lint.py <path> [path ...]")
        print("  Lint markdown files or directories for conversion issues.")
        sys.exit(1)

    total_errors = 0
    for arg in sys.argv[1:]:
        path = Path(arg)
        if path.is_dir():
            results = lint_directory(path)
        elif path.is_file():
            issues = lint_file(path)
            results = {str(path): issues} if issues else {}
        else:
            print(f"Not found: {arg}")
            continue

        if results:
            total_errors += print_results(results)
        else:
            print(f"  ✅ {arg}: no issues found")

    if total_errors:
        print(f"\n❌ {total_errors} error(s) found — fix before converting.")
        sys.exit(1)
    else:
        print("\n✅ All clear — safe to convert.")


if __name__ == "__main__":
    main()
