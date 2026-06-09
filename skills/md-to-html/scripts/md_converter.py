#!/usr/bin/env python3
"""Zero-dependency Markdown-to-HTML converter.

Supports: headings, bold/italic/code, links, images, tables, fenced code,
mermaid blocks, callouts ([!WARNING] etc.), blockquotes, ordered/unordered lists.

Link rewriting modes:
  - anchor_map: dict mapping relative paths to #anchor slugs (single-page)
  - known_pages + page context: set of html_rel paths (multi-page)
"""

import html
import re

CALLOUT_TYPES = {"WARNING", "NOTE", "TIP", "IMPORTANT", "CAUTION"}


def _escape(text: str) -> str:
    return html.escape(text, quote=False)


def slugify(text: str) -> str:
    """Convert heading text to a URL-safe slug.

    Decodes HTML entities first so emoji / special chars are stripped rather
    than leaving their hex codes in the slug (e.g. ``&#x1F517;`` decodes to
    a non-alphanumeric char that is then removed, instead of leaking
    ``x1f517`` into the id).

    This is the **single** slugifier used for heading ``id=`` attributes AND
    for normalising ``#fragment`` links — using the same function for both
    guarantees they always agree.
    """
    text = html.unescape(text)
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


# ── Link rewriting ───────────────────────────────────────────────────────────


def _normalize_fragment(fragment: str) -> str:
    """Normalise a ``#fragment`` through the same slugifier used for heading ids.

    Accepts either ``#some-slug`` or bare ``some-slug``; always returns with
    the leading ``#``. Returns ``""`` for empty/blank input.
    """
    raw = fragment.lstrip("#")
    if not raw:
        return ""
    return "#" + slugify(raw)


def _rewrite_href_anchor(href: str, anchor_map: dict[str, str]) -> str:
    """Rewrite href using an anchor map (single-page mode)."""
    if href.startswith(("http://", "https://", "mailto:")):
        return href
    if href.startswith("#"):
        return _normalize_fragment(href)
    fragment = ""
    if "#" in href:
        href, fragment = href.split("#", 1)
        fragment = _normalize_fragment(fragment)
    if not href:
        return fragment

    import posixpath

    clean = href.replace("\\", "/")
    while clean.startswith("../"):
        clean = clean[3:]
    if clean.startswith("./"):
        clean = clean[2:]
    clean = posixpath.normpath(clean)

    candidates = [clean]
    if clean.endswith(".md"):
        candidates += [clean[:-3] + ".html", clean[:-3]]
    elif clean.endswith(".html"):
        candidates += [clean[:-5] + ".md", clean[:-5]]
    else:
        candidates += [clean + ".md", clean + ".html"]

    for c in candidates:
        if c in anchor_map:
            return anchor_map[c] + fragment
    return href + fragment


def _relative_link(from_html: str, to_html: str) -> str:
    """Compute a relative link between two html paths."""
    from_parts = from_html.replace("\\", "/").split("/")
    to_parts = to_html.replace("\\", "/").split("/")
    from_dir = from_parts[:-1]
    to_dir = to_parts[:-1]
    common = 0
    for a, b in zip(from_dir, to_dir):
        if a == b:
            common += 1
        else:
            break
    ups = len(from_dir) - common
    rel = [".."] * ups + to_parts[common:]
    return "/".join(rel) if rel else to_parts[-1]


def _rewrite_href_multipage(
    href: str,
    page_dir: str,
    page_html_rel: str,
    known_pages: set[str] | None,
) -> str | None:
    """Rewrite href for multi-page mode with relative path resolution.

    Returns the rewritten ``.html`` href, or ``None`` to signal that the
    target is not a published page and the link should be emitted as plain
    text (un-linked). Returning ``None`` instead of fabricating a ``.html``
    href is what prevents dangling 404 links to underscore-prefixed working
    files (e.g. ``_Manifest.md``) and out-of-site targets (``README.md``,
    ``AGENTS.md``, ADRs under ``notes/``). See bead_chain-w8w.
    """
    if href.startswith(("http://", "https://", "mailto:")):
        return href
    if href.startswith("#"):
        return _normalize_fragment(href)
    anchor = ""
    if "#" in href:
        href, anchor = href.split("#", 1)
        anchor = _normalize_fragment(anchor)
    if not href:
        return anchor
    if href.lower().endswith(".md"):
        href = href[:-3]
    elif href.lower().endswith(".html"):
        href = href[:-5]

    import posixpath

    file_rel = posixpath.normpath(f"{page_dir}/{href}" if page_dir else href)
    root_rel = posixpath.normpath(href)

    if known_pages is not None:
        if f"{file_rel}.html" in known_pages:
            resolved = file_rel
        elif f"{root_rel}.html" in known_pages:
            resolved = root_rel
        else:
            # Target is neither a file-relative nor a root-relative
            # published page. Do NOT fabricate a ``.html`` href that will
            # 404; signal the caller to keep the link text but drop the
            # broken link. (bead_chain-w8w)
            return None
    else:
        # No published-page set to validate against (e.g. a standalone
        # conversion); preserve the legacy best-effort resolution.
        resolved = file_rel

    target_html = f"{resolved}.html"
    if page_html_rel:
        return _relative_link(page_html_rel, target_html) + anchor
    return target_html + anchor


# ── Front matter & HTML passthrough ─────────────────────────────────────────


def _strip_front_matter(text: str) -> str:
    """Remove YAML front matter (--- delimited block at start of file)."""
    if not text.startswith("---"):
        return text
    end = text.find("\n---", 3)
    if end == -1:
        return text
    # Skip past the closing --- and the newline after it
    rest = text[end + 4 :]
    return rest.lstrip("\n")


# HTML block tags that signal raw HTML passthrough
_HTML_BLOCK_RE = re.compile(
    r"^\s*</?(?:div|section|aside|header|footer|nav|main|article|figure|"
    r"figcaption|details|summary|style|script|table|thead|tbody|tr|th|td|"
    r"iframe|form|fieldset|p|ul|ol|li|dl|dt|dd|h[1-6]|br|hr)"
    r"[\s>/]",
    re.IGNORECASE,
)


def _is_html_block(line: str) -> bool:
    """Detect lines that start with raw HTML block elements."""
    stripped = line.strip()
    if not stripped.startswith("<"):
        return False
    return _HTML_BLOCK_RE.match(stripped) is not None


# ── Inline formatting ────────────────────────────────────────────────────────


def _inline_format(text: str, rewrite_fn) -> str:
    """Bold and italic, applied to text outside images/links/code spans.

    Preserves inline HTML tags (e.g. <span class="badge">) by extracting
    them before escaping, then reinserting after.

    Note: image and link parsing is handled by ``convert_inline`` so that
    code spans inside link text render correctly. ``rewrite_fn`` is kept in
    the signature for forward compatibility but is currently unused here.
    """
    del rewrite_fn  # signature kept for symmetry; not used at this layer

    # Extract HTML tags, replace with placeholders, escape the rest, restore
    tags: list[str] = []

    def _stash_tag(m: re.Match) -> str:
        tags.append(m.group(0))
        return f"\x00TAG{len(tags) - 1}\x00"

    t = re.sub(r"<[^>]+>", _stash_tag, text)
    t = _escape(t)
    for idx, tag in enumerate(tags):
        t = t.replace(f"\x00TAG{idx}\x00", tag)

    t = re.sub(r"\*\*\*(.+?)\*\*\*", r"<strong><em>\1</em></strong>", t)
    t = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", t)
    t = re.sub(r"\*(.+?)\*", r"<em>\1</em>", t)
    return t


# Single tokenizer for images, links, and code spans. Leftmost match wins;
# alternation order resolves ties (image > link > code, since `!` can't start
# a link or code span).
_INLINE_TOKEN_RE = re.compile(
    r"!\[(?P<img_alt>[^\]]*)\]\((?P<img_src>[^)]+)\)"
    r"|\[(?P<link_text>[^\]]+)\]\((?P<link_href>[^)]+)\)"
    r"|`(?P<code_text>[^`]+)`"
)


def convert_inline(text: str, rewrite_fn) -> str:
    """Convert inline markdown.

    Tokenizes images, links, and code spans in a single leftmost-wins pass.
    Link text is recursively processed so code/bold/italic work inside links
    (e.g. ``[`foo`](url)`` renders as ``<a href="url"><code>foo</code></a>``).
    Text outside these tokens is processed by ``_inline_format`` for bold,
    italic, HTML escaping, and inline HTML tag preservation.
    """
    parts: list[str] = []
    last = 0
    for m in _INLINE_TOKEN_RE.finditer(text):
        if m.start() > last:
            parts.append(_inline_format(text[last : m.start()], rewrite_fn))

        if m.group("img_src") is not None:
            alt = _escape(m.group("img_alt"))
            src = _escape(m.group("img_src"))
            parts.append(f'<img alt="{alt}" src="{src}" style="max-width:100%">')
        elif m.group("link_text") is not None:
            inner = convert_inline(m.group("link_text"), rewrite_fn)
            new_href = rewrite_fn(m.group("link_href"))
            if new_href is None:
                # Target is not a published page: keep the visible label
                # but drop the broken link rather than emit a dangling
                # href. (bead_chain-w8w)
                parts.append(inner)
            else:
                href = _escape(new_href)
                parts.append(f'<a href="{href}">{inner}</a>')
        else:  # code span
            parts.append(f"<code>{_escape(m.group('code_text'))}</code>")

        last = m.end()

    if last < len(text):
        parts.append(_inline_format(text[last:], rewrite_fn))
    return "".join(parts)


# ── Post-build guard ─────────────────────────────────────────────────────────

# A literal markdown link to a .md file that survived conversion, e.g.
# ``[some text](../foo/bar.md)``. The length caps keep the match from running
# away across an entire document if a stray bracket appears.
_UNCONVERTED_LINK_RE = re.compile(r"\[[^\]\n]{1,300}\]\([^)\n]{0,300}\.md[^)\n]*\)")
_PRE_BLOCK_RE = re.compile(r"<pre\b.*?</pre>", re.DOTALL | re.IGNORECASE)
_CODE_SPAN_RE = re.compile(r"<code\b.*?</code>", re.DOTALL | re.IGNORECASE)


def find_unconverted_links(html_text: str) -> list[str]:
    """Return literal markdown ``.md`` links left unconverted in HTML output.

    Code blocks (``<pre>``) and inline code spans (``<code>``) are scrubbed
    first so legitimate markdown examples in documentation don't trip the
    guard. A non-empty result means the converter leaked raw ``[text](x.md)``
    syntax into rendered prose — the failure mode this guard exists to catch.
    """
    scrubbed = _PRE_BLOCK_RE.sub("", html_text)
    scrubbed = _CODE_SPAN_RE.sub("", scrubbed)
    return _UNCONVERTED_LINK_RE.findall(scrubbed)


# ── Converter class ──────────────────────────────────────────────────────────


class MarkdownConverter:
    """Line-by-line markdown to HTML converter.

    Supports two link-rewriting modes:
      - anchor_map: for single-page builds (maps paths to #anchors)
      - known_pages + page context: for multi-page builds (relative .html links)
    """

    def __init__(
        self,
        anchor_map: dict[str, str] | None = None,
        known_pages: set[str] | None = None,
    ):
        self.anchor_map = anchor_map
        self.known_pages = known_pages
        self.lines: list[str] = []
        self.out: list[str] = []
        self.i = 0
        self.title = ""
        self._page_dir = ""
        self._page_html_rel = ""

    def convert(
        self,
        md_text: str,
        page_dir: str = "",
        page_html_rel: str = "",
    ) -> tuple[str, str]:
        """Return (html_body, page_title)."""
        # Strip YAML front matter (--- delimited block at start)
        md_text = _strip_front_matter(md_text)

        self.lines = md_text.split("\n")
        self.out = []
        self.i = 0
        self.title = ""
        self._page_dir = page_dir
        self._page_html_rel = page_html_rel

        while self.i < len(self.lines):
            line = self.lines[self.i]
            if line.strip().startswith("```"):
                self._fenced_code()
            elif hm := re.match(r"^(#{1,6})\s+(.+)$", line):
                self._heading(hm)
            elif _is_html_block(line):
                self._html_block()
            elif re.match(r"^---+\s*$", line):
                self.out.append("<hr>")
                self.i += 1
            elif "|" in line and self._peek_table_sep():
                self._table()
            elif re.match(r"^>\s*\[!(WARNING|NOTE|TIP|IMPORTANT|CAUTION)\]", line):
                self._callout()
            elif line.startswith("> ") or line.strip() == ">":
                self._blockquote()
            elif re.match(r"^\s*\d+\.\s", line):
                self._list(ordered=True)
            elif re.match(r"^\s*[-*+]\s", line):
                self._list(ordered=False)
            elif not line.strip():
                self.i += 1
            else:
                self._paragraph()

        return "\n".join(self.out), self.title

    def _rewrite(self, href: str) -> str | None:
        """Route to the correct link rewriter based on mode.

        Returns ``None`` only in multi-page mode when the target is not a
        published page (see ``_rewrite_href_multipage``); anchor mode always
        returns a string.
        """
        if self.anchor_map is not None:
            return _rewrite_href_anchor(href, self.anchor_map)
        return _rewrite_href_multipage(
            href,
            self._page_dir,
            self._page_html_rel,
            self.known_pages,
        )

    def _inline(self, text: str) -> str:
        return convert_inline(text, self._rewrite)

    def _peek_table_sep(self) -> bool:
        return (
            self.i + 1 < len(self.lines)
            and re.match(r"^\s*\|[\s:|-]+\|\s*$", self.lines[self.i + 1]) is not None
        )

    def _heading(self, hm: re.Match):
        level = len(hm.group(1))
        text = hm.group(2).strip()
        slug = slugify(text)
        self.out.append(f'<h{level} id="{slug}">{self._inline(text)}</h{level}>')
        if level == 1 and not self.title:
            self.title = text
        self.i += 1

    def _html_block(self):
        """Pass through raw HTML block lines verbatim."""
        block: list[str] = []
        while self.i < len(self.lines):
            line = self.lines[self.i]
            if not line.strip() and block:
                # Blank line ends the HTML block
                break
            if (
                block
                and not _is_html_block(line)
                and not line.strip().startswith("<")
                and not line.strip().startswith("</")
                and line.strip()
            ):
                # Non-HTML content line after HTML started — keep if inside tags
                block.append(line)
                self.i += 1
                continue
            block.append(line)
            self.i += 1
        self.out.append("\n".join(block))

    def _fenced_code(self):
        lang = self.lines[self.i].strip().lstrip("`").strip()
        self.i += 1
        code_lines: list[str] = []
        while self.i < len(self.lines):
            if self.lines[self.i].strip().startswith("```"):
                self.i += 1
                break
            code_lines.append(self.lines[self.i])
            self.i += 1
        code = _escape("\n".join(code_lines))
        if lang.lower() == "mermaid":
            self.out.append(f'<pre class="mermaid">\n{code}\n</pre>')
        elif lang:
            self.out.append(
                f'<pre><code class="language-{_escape(lang)}">{code}</code></pre>'
            )
        else:
            self.out.append(f"<pre><code>{code}</code></pre>")

    def _table(self):
        rows: list[list[str]] = []
        while self.i < len(self.lines) and "|" in self.lines[self.i]:
            cells = [
                c.strip() for c in self.lines[self.i].strip().strip("|").split("|")
            ]
            rows.append(cells)
            self.i += 1
        if len(rows) < 2:
            return
        self.out.append("<table><thead><tr>")
        for cell in rows[0]:
            self.out.append(f"<th>{self._inline(cell)}</th>")
        self.out.append("</tr></thead><tbody>")
        for row in rows[2:]:
            self.out.append("<tr>")
            for cell in row:
                self.out.append(f"<td>{self._inline(cell)}</td>")
            self.out.append("</tr>")
        self.out.append("</tbody></table>")

    def _callout(self):
        m = re.match(r"^>\s*\[!(\w+)\]\s*(.*)", self.lines[self.i])
        ctype = m.group(1) if m else "NOTE"
        first = (m.group(2) or "").strip() if m else ""
        self.i += 1
        body_lines = [first] if first else []
        while self.i < len(self.lines):
            line = self.lines[self.i]
            if line.startswith("> "):
                body_lines.append(line[2:])
                self.i += 1
            elif line.strip() == ">":
                body_lines.append("")
                self.i += 1
            else:
                break
        body = self._inline(" ".join(ln for ln in body_lines if ln.strip()))
        self.out.append(
            f'<div class="callout callout-{ctype.lower()}">'
            f'<div class="callout-title">{ctype}</div>'
            f"<p>{body}</p></div>"
        )

    def _blockquote(self):
        lines: list[str] = []
        while self.i < len(self.lines):
            line = self.lines[self.i]
            if line.startswith("> "):
                lines.append(line[2:])
                self.i += 1
            elif line.strip() == ">":
                lines.append("")
                self.i += 1
            else:
                break
        self.out.append(
            f"<blockquote><p>{self._inline(chr(10).join(lines))}</p></blockquote>"
        )

    def _starts_block(self, line: str) -> bool:
        """True if ``line`` begins a new block-level construct.

        Used to decide whether an unindented, non-blank line is a *lazy
        continuation* of the current list item (CommonMark behaviour) or a
        genuine new block that should terminate the list.
        """
        if re.match(r"^#{1,6}\s", line):
            return True
        if line.strip().startswith("```"):
            return True
        if re.match(r"^---+\s*$", line):
            return True
        if re.match(r"^>\s", line) or line.strip() == ">":
            return True
        if "|" in line and self._peek_table_sep():
            return True
        return _is_html_block(line)

    def _list(self, ordered: bool):
        """Parse a list. Items can contain:
          - inline continuation (indented OR lazily-unindented plain text —
            joined into the <li> text before inline conversion, so links whose
            text wraps across source lines still resolve)
          - fenced code blocks (indented ```; emitted as <pre> inside the <li>)
          - blank lines that don't end the list (next non-blank is a new item
            or indented)

        Raw item text is accumulated and converted with ``_inline`` only at
        flush time. Converting per-line would feed a multi-line markdown link
        to the regex one fragment at a time, leaking literal ``[text](x.md)``
        into the output — the bug this method guards against.
        """
        tag = "ol" if ordered else "ul"
        item_re = re.compile(r"^\s*\d+\.\s" if ordered else r"^\s*[-*+]\s")
        fence_re = re.compile(r"^\s*```")

        self.out.append(f"<{tag}>")
        cur_raw: str | None = None
        cur_blocks: list[str] = []

        def flush():
            nonlocal cur_raw, cur_blocks
            if cur_raw is not None:
                blocks = "".join(cur_blocks)
                self.out.append(f"<li>{self._inline(cur_raw)}{blocks}</li>")
                cur_raw = None
                cur_blocks = []

        while self.i < len(self.lines):
            line = self.lines[self.i]

            # New list item at this level
            if item_re.match(line):
                flush()
                text = item_re.sub("", line, count=1)
                cur_raw = text.strip()
                self.i += 1
                continue

            # Everything below only makes sense once we're inside an item
            if cur_raw is None:
                break

            # Fenced code block indented inside the current item
            if fence_re.match(line):
                indent = len(line) - len(line.lstrip())
                lang = line.strip().lstrip("`").strip()
                self.i += 1
                code_lines: list[str] = []
                while self.i < len(self.lines):
                    nxt = self.lines[self.i]
                    if nxt.lstrip().startswith("```"):
                        self.i += 1
                        break
                    # Dedent by the fence's indent when possible
                    if len(nxt) >= indent and nxt[:indent].strip() == "":
                        code_lines.append(nxt[indent:])
                    else:
                        code_lines.append(nxt)
                    self.i += 1
                code = _escape("\n".join(code_lines))
                if lang.lower() == "mermaid":
                    cur_blocks.append(f'<pre class="mermaid">\n{code}\n</pre>')
                elif lang:
                    cur_blocks.append(
                        f'<pre><code class="language-{_escape(lang)}">{code}</code></pre>'
                    )
                else:
                    cur_blocks.append(f"<pre><code>{code}</code></pre>")
                continue

            # Plain indented continuation — join into current item's raw text
            if line.startswith("  ") or line.startswith("\t"):
                cur_raw = (cur_raw or "") + " " + line.strip()
                self.i += 1
                continue

            # Blank line: keep the list going if the next non-blank is still part of it
            if not line.strip():
                j = self.i + 1
                while j < len(self.lines) and not self.lines[j].strip():
                    j += 1
                if j < len(self.lines):
                    nxt = self.lines[j]
                    if (
                        item_re.match(nxt)
                        or nxt.startswith("  ")
                        or nxt.startswith("\t")
                    ):
                        self.i += 1
                        continue
                break

            # Lazy continuation: an unindented, non-blank line that doesn't
            # start a new block belongs to the current item's paragraph. This
            # rescues markdown links whose text wraps onto an unindented line.
            if not self._starts_block(line):
                cur_raw = (cur_raw or "") + " " + line.strip()
                self.i += 1
                continue

            break

        flush()
        self.out.append(f"</{tag}>")

    def _paragraph(self):
        lines: list[str] = []
        while self.i < len(self.lines):
            line = self.lines[self.i]
            if not line.strip():
                break
            if re.match(r"^#{1,6}\s", line):
                break
            if line.strip().startswith("```"):
                break
            if re.match(r"^\s*[-*+]\s", line) or re.match(r"^\s*\d+\.\s", line):
                break
            if "|" in line and self._peek_table_sep():
                break
            if re.match(r"^>\s", line):
                break
            if re.match(r"^---+\s*$", line):
                break
            lines.append(line)
            self.i += 1
        if lines:
            self.out.append(
                f"<p>{self._inline(' '.join(ln.strip() for ln in lines))}</p>"
            )
