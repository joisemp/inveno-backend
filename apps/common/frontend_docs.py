"""
Helpers for the Swagger Frontend guide tab.

Renders ``frontend_guide.md`` without a Markdown package, and lists public
API operations from a Spectacular schema so the endpoint table stays in sync.
"""
import re
from html import escape
from pathlib import Path

from django.conf import settings

FRONTEND_GUIDE_PATH = Path(__file__).resolve().parent / "frontend_guide.md"

# Docs chrome — omitted from the live endpoint index.
DOCS_PATHS = frozenset(
    {
        "/api/docs/",
        "/api/docs/frontend/",
        "/api/redoc/",
        "/api/schema/",
    }
)

_HTTP_METHODS = ("get", "post", "put", "patch", "delete", "head", "options")

_FENCE_RE = re.compile(r"^```(\w*)\s*$")
_HEADING_RE = re.compile(r"^(#{1,6})\s+(.*)$")
_UL_RE = re.compile(r"^[-*]\s+(.*)$")
_OL_RE = re.compile(r"^(\d+)\.\s+(.*)$")
_HR_RE = re.compile(r"^(-{3,}|\*{3,})$")
_TABLE_SEP_RE = re.compile(r"^\|?\s*:?-{3,}:?\s*(\|\s*:?-{3,}:?\s*)+\|?\s*$")


def load_frontend_guide() -> str:
    """Return the Frontend guide markdown source."""
    return FRONTEND_GUIDE_PATH.read_text(encoding="utf-8")


def public_api_operations(schema: dict) -> list[dict]:
    """
    Flatten OpenAPI paths into ``{method, path, summary}`` rows.

    Skips documentation routes so the Frontend tab lists product API only.
    """
    rows: list[dict] = []
    paths = schema.get("paths") or {}
    for path in sorted(paths):
        if path in DOCS_PATHS:
            continue
        item = paths[path] or {}
        for method in _HTTP_METHODS:
            operation = item.get(method)
            if not isinstance(operation, dict):
                continue
            rows.append(
                {
                    "method": method.upper(),
                    "path": path,
                    "summary": operation.get("summary") or "",
                }
            )
    return rows


def markdown_to_html(source: str) -> str:
    """
    Convert the Frontend guide Markdown subset to HTML.

    Supports ATX headings, fenced code, tables, lists, blockquotes, hr,
    paragraphs, and inline ``code`` / **bold** / links. No third-party dep.
    """
    lines = source.replace("\r\n", "\n").split("\n")
    blocks: list[str] = []
    i = 0
    n = len(lines)

    while i < n:
        line = lines[i]
        stripped = line.strip()

        if not stripped:
            i += 1
            continue

        fence = _FENCE_RE.match(stripped)
        if fence:
            lang = fence.group(1)
            body: list[str] = []
            i += 1
            while i < n and not _FENCE_RE.match(lines[i].strip()):
                body.append(lines[i])
                i += 1
            if i < n:
                i += 1
            cls = f' class="language-{escape(lang)}"' if lang else ""
            code = escape("\n".join(body), quote=False)
            blocks.append(f"<pre><code{cls}>{code}</code></pre>")
            continue

        heading = _HEADING_RE.match(stripped)
        if heading:
            level = len(heading.group(1))
            blocks.append(
                f"<h{level}>{_inline(heading.group(2))}</h{level}>"
            )
            i += 1
            continue

        if _HR_RE.match(stripped):
            blocks.append("<hr>")
            i += 1
            continue

        if stripped.startswith(">"):
            quote: list[str] = []
            while i < n and lines[i].strip().startswith(">"):
                quote.append(lines[i].strip()[1:].lstrip())
                i += 1
            inner = " ".join(quote)
            blocks.append(f"<blockquote><p>{_inline(inner)}</p></blockquote>")
            continue

        if "|" in stripped and i + 1 < n and _TABLE_SEP_RE.match(lines[i + 1].strip()):
            header = _split_table_row(stripped)
            i += 2
            rows: list[list[str]] = []
            while i < n and lines[i].strip().startswith("|"):
                rows.append(_split_table_row(lines[i].strip()))
                i += 1
            thead = "".join(f"<th>{_inline(c)}</th>" for c in header)
            body_html = []
            for row in rows:
                tds = "".join(f"<td>{_inline(c)}</td>" for c in row)
                body_html.append(f"<tr>{tds}</tr>")
            blocks.append(
                "<table><thead><tr>"
                + thead
                + "</tr></thead><tbody>"
                + "".join(body_html)
                + "</tbody></table>"
            )
            continue

        ul_match = _UL_RE.match(stripped)
        if ul_match:
            items: list[str] = []
            while i < n:
                m = _UL_RE.match(lines[i].strip())
                if not m:
                    break
                items.append(f"<li>{_inline(m.group(1))}</li>")
                i += 1
            blocks.append("<ul>" + "".join(items) + "</ul>")
            continue

        ol_match = _OL_RE.match(stripped)
        if ol_match:
            items = []
            while i < n:
                m = _OL_RE.match(lines[i].strip())
                if not m:
                    break
                items.append(f"<li>{_inline(m.group(2))}</li>")
                i += 1
            blocks.append("<ol>" + "".join(items) + "</ol>")
            continue

        para: list[str] = []
        while i < n and lines[i].strip():
            peek = lines[i].strip()
            if (
                _FENCE_RE.match(peek)
                or _HEADING_RE.match(peek)
                or _HR_RE.match(peek)
                or peek.startswith(">")
                or _UL_RE.match(peek)
                or _OL_RE.match(peek)
            ):
                break
            if "|" in peek and i + 1 < n and _TABLE_SEP_RE.match(lines[i + 1].strip()):
                break
            para.append(peek)
            i += 1
        if para:
            blocks.append(f"<p>{_inline(' '.join(para))}</p>")

    return "\n".join(blocks)


def _split_table_row(row: str) -> list[str]:
    cells = [c.strip() for c in row.strip().strip("|").split("|")]
    return cells


_CODE_INLINE_RE = re.compile(r"`([^`]+)`")
_BOLD_RE = re.compile(r"\*\*([^*]+)\*\*")
_LINK_RE = re.compile(r"\[([^\]]+)\]\(([^)]+)\)")


def _inline(text: str) -> str:
    """Escape HTML then apply inline Markdown."""
    placeholders: list[str] = []

    def stash_code(match: re.Match) -> str:
        placeholders.append(f"<code>{escape(match.group(1))}</code>")
        return f"\x00{len(placeholders) - 1}\x00"

    text = _CODE_INLINE_RE.sub(stash_code, text)
    text = escape(text)

    def restore(match: re.Match) -> str:
        return placeholders[int(match.group(1))]

    text = re.sub(r"\x00(\d+)\x00", restore, text)
    text = _BOLD_RE.sub(r"<strong>\1</strong>", text)
    text = _LINK_RE.sub(r'<a href="\2">\1</a>', text)
    return text


def spectacular_favicon() -> str:
    """Favicon URL used by the custom Swagger chrome."""
    return settings.SPECTACULAR_SETTINGS.get("SWAGGER_UI_FAVICON_HREF", "")
