"""HTML translation logic."""

import html as html_lib
import re
import time
from typing import Callable

from bs4 import BeautifulSoup, Tag
from bs4.element import NavigableString

from .engines import EMPHASIS_TAGS, ENGINES

# Tags whose text content should be translated
TRANSLATE_TAGS = {"p", "h1", "h2", "h3", "h4", "h5", "h6", "li", "td", "th"}

# Tags that act as block boundaries (must not be nested inside each other)
BLOCK_TAGS = TRANSLATE_TAGS

# Tags whose subtree should never be translated
PRESERVE_TAGS = {"table", "style", "script"}

# CSS classes whose subtree should never be translated
PRESERVE_CLASSES = {"note", "footnote"}

# Progress callback: (batch_number, total_batches, batch_chars)
ProgressCallback = Callable[[int, int, int], None]

# Matches any tag that isn't an emphasis tag — used to strip everything else
# from the LLM's output.
_STRIP_TAGS_RE = re.compile(rf"<(?!/?(?:{'|'.join(EMPHASIS_TAGS)})\b)[^>]+>", re.I)


def _should_preserve(tag, preserve_tags: set[str], preserve_classes: set[str]) -> bool:
    """Check if *tag* (or any of its ancestors) should be preserved."""
    for current in [tag, *tag.parents]:
        if getattr(current, "name", None) in preserve_tags:
            return True
        classes = current.get("class", []) if hasattr(current, "get") else []
        if isinstance(classes, str):
            classes = classes.split()
        if any(cls in preserve_classes for cls in classes):
            return True
    return False


def _get_translatable_nodes(soup):
    """Return all translatable tag nodes from a BeautifulSoup *soup*."""
    return [
        tag
        for tag in soup.find_all(TRANSLATE_TAGS)
        if tag.get_text(strip=True)
        and not tag.find(BLOCK_TAGS)
        and not _should_preserve(tag, PRESERVE_TAGS, PRESERVE_CLASSES)
    ]


def count_translatable_chars(html_bytes: bytes) -> int:
    """Count total characters in translatable text nodes (without actually translating)."""
    soup = BeautifulSoup(html_bytes, "lxml-xml")
    nodes = _get_translatable_nodes(soup)
    return sum(len(_extract_text_with_emphasis(node)) for node in nodes)


def _extract_text_with_emphasis(node: Tag) -> str:
    """Extract text content keeping only emphasis tags for translation.

    e.g. ``<p>Hello <em>world</em> <span class="x">!</span></p>``
         → ``"Hello <em>world</em> !"``
    """
    parts: list[str] = []
    for child in node.children:
        if isinstance(child, NavigableString):
            parts.append(str(child))
        elif isinstance(child, Tag) and child.name in EMPHASIS_TAGS:
            inner = _extract_text_with_emphasis(child)
            parts.append(f"<{child.name}>{inner}</{child.name}>")
        else:
            parts.append(child.get_text())
    return "".join(parts).strip()


def _flatten_texts(parts: list[str]) -> str:
    """Join text parts, stripping empty strings."""
    return " ".join(part.strip() for part in parts if part.strip())


def _clean_translated(raw: str) -> str:
    """Sanitise the LLM's output: keep only known emphasis tags, strip the rest."""
    return _STRIP_TAGS_RE.sub("", raw.strip()).strip()


# Pre-compiled regex for emphasis tag splitting
_EMPHASIS_RE = re.compile(r"(</?(?:em|strong|b|i)\s*/?>)")


def translate_html(
    html_bytes: bytes,
    engine: str,
    creativity: float | None = None,
    progress_cb: ProgressCallback | None = None,
) -> tuple[bytes, int]:
    """Translate all translatable text nodes in *html_bytes*.

    Returns ``(translated_html_bytes, total_char_count)``.

    If *progress_cb* is provided, it is called after each API batch completes
    with ``(batch_number, total_batches, batch_chars)`` so the caller can
    display per-chapter progress.
    """
    cfg = ENGINES[engine]
    soup = BeautifulSoup(html_bytes, "lxml-xml")
    nodes = _get_translatable_nodes(soup)
    if not nodes:
        return html_bytes, 0

    # Extract each element as simplified text — plain text + emphasis tags only
    texts: list[str] = [_extract_text_with_emphasis(node) for node in nodes]
    char_count = sum(len(t) for t in texts)

    # ── Pre-compute batches ────────────────────────────────────────────────────
    batches: list[list[str]] = []
    cur_batch: list[str] = []
    cur_len = 0

    for text in texts:
        if (
            cur_len + len(text) > cfg.char_limit or len(cur_batch) >= cfg.elem_limit
        ) and cur_batch:
            batches.append(cur_batch)
            cur_batch, cur_len = [], 0
        cur_batch.append(text)
        cur_len += len(text)
    if cur_batch:
        batches.append(cur_batch)

    total_batches = len(batches)

    # ── Translate each batch ──────────────────────────────────────────────────
    def translate_batch(batch_texts: list[str]) -> list[str]:
        try:
            result = cfg.translate(batch_texts, creativity=creativity)
            if len(result) == len(batch_texts):
                return result
            # Mismatched count — split and retry
        except Exception:
            # API failure (400, JSON parse, etc.) — split and retry
            pass

        if len(batch_texts) == 1:
            # Single element failed — return original text as fallback
            return [_flatten_texts(batch_texts)]
        mid = len(batch_texts) // 2
        return translate_batch(batch_texts[:mid]) + translate_batch(batch_texts[mid:])

    translated_all: list[str] = []
    for i, batch in enumerate(batches):
        if cfg.delay and i > 0:
            time.sleep(cfg.delay)
        translated_all.extend(translate_batch(batch))
        if progress_cb:
            progress_cb(i + 1, total_batches, sum(len(t) for t in batch))

    # Write translated content back into each element
    for node, translated in zip(nodes, translated_all):
        cleaned = _clean_translated(translated)
        node.clear()
        if "<" in cleaned:
            # HTML-escape text segments so literal <, >, & don't break XML parsing
            parts = _EMPHASIS_RE.split(cleaned)
            for i in range(0, len(parts), 2):
                parts[i] = html_lib.escape(parts[i], quote=False)
            escaped = "".join(parts)
            frag = BeautifulSoup(f"<x>{escaped}</x>", "lxml-xml").find("x")
            for child in list(frag.children):
                node.append(child)
        else:
            node.append(NavigableString(cleaned))

    return soup.encode("utf-8"), char_count
