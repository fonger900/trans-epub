"""HTML translation logic."""

from __future__ import annotations

import html as html_lib
import re
import time
from typing import Callable

from bs4 import BeautifulSoup, Tag
from bs4.element import NavigableString

from .config import Glossary
from .engines.base import EMPHASIS_TAGS, ENGINES

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


def _should_preserve(
    tag: Tag, preserve_tags: set[str], preserve_classes: set[str]
) -> bool:
    """Check if *tag* (or any of its ancestors) should be preserved."""
    for current in [tag, *tag.parents]:
        if getattr(current, "name", None) in preserve_tags:
            return True
        if hasattr(current, "get"):
            classes: list[str] | str = current.get("class") or []  # type: ignore[assignment]
            if isinstance(classes, str):
                classes = classes.split()
            if any(cls in preserve_classes for cls in classes):
                return True
    return False


def _get_translatable_nodes(soup: BeautifulSoup) -> list[Tag]:
    """Return all translatable tag nodes from a BeautifulSoup *soup*."""
    return [
        tag
        for tag in soup.find_all(TRANSLATE_TAGS)
        if tag.get_text(strip=True)
        and not tag.find(BLOCK_TAGS)
        and not _should_preserve(tag, PRESERVE_TAGS, PRESERVE_CLASSES)
    ]


def count_translatable_chars(html_bytes: bytes) -> int:
    """Count total characters in translatable text nodes and attributes."""
    soup = BeautifulSoup(html_bytes, "lxml-xml")
    nodes = _get_translatable_nodes(soup)
    text_chars = sum(len(_extract_text_with_emphasis(node)) for node in nodes)
    attrs = _collect_translatable_attributes(soup, nodes)
    attr_chars = sum(len(val) for _, _, val in attrs)
    return text_chars + attr_chars


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


def _collect_translatable_attributes(soup: BeautifulSoup, nodes: list[Tag]) -> list:
    """Collect translatable attribute values from within text nodes.

    Returns a list of (tag, attr_name, attr_value) tuples.
    Skips attributes inside preserved blocks.
    """
    results: list = []
    seen: set = set()

    def collect(tag: Tag) -> None:
        tid = id(tag)
        if tid in seen:
            return
        seen.add(tid)
        for attr in _ATTRS_TO_TRANSLATE:
            value = tag.get(attr)
            if isinstance(value, str) and value.strip():
                results.append((tag, attr, value.strip()))

    # Scan within translatable nodes for child elements with attributes
    for node in nodes:
        for child in node.find_all():
            if not isinstance(child, Tag):
                continue
            if _should_preserve(child, PRESERVE_TAGS, PRESERVE_CLASSES):
                continue
            collect(child)

    # Also scan standalone attribute-bearing tags at document level
    for tag_name in _STANDALONE_ATTR_TAGS:
        for tag_elem in soup.find_all(tag_name):
            if not isinstance(tag_elem, Tag):
                continue
            if _should_preserve(tag_elem, PRESERVE_TAGS, PRESERVE_CLASSES):
                continue
            collect(tag_elem)

    return results


def _flatten_texts(parts: list[str]) -> str:
    """Join text parts, stripping empty strings."""
    return " ".join(part.strip() for part in parts if part.strip())


def _clean_translated(raw: str) -> str:
    """Sanitise the LLM's output: keep only known emphasis tags, strip the rest."""
    return _STRIP_TAGS_RE.sub("", raw.strip()).strip()


# Pre-compiled regex for emphasis tag splitting
_EMPHASIS_RE = re.compile(r"(</?(?:em|strong|b|i)\s*/?>)")

# HTML attributes whose values should be translated
_ATTRS_TO_TRANSLATE = {"alt", "title", "placeholder", "aria-label"}

# Tags whose translatable attributes are collected even outside text blocks
# (e.g., standalone img tags at body level often have meaningful alt text)
_STANDALONE_ATTR_TAGS = {"img"}


def translate_html(
    html_bytes: bytes,
    engine: str,
    creativity: float | None = None,
    progress_cb: ProgressCallback | None = None,
    glossary: Glossary | None = None,
    extra_prompt: str = "",
    cached_soup: BeautifulSoup | None = None,
    cached_nodes: list[Tag] | None = None,
    cached_attrs: list | None = None,
) -> tuple[bytes, int]:
    """Translate all translatable text nodes in *html_bytes*.

    Returns ``(translated_html_bytes, total_char_count)``.

    If *cached_soup*/*cached_nodes*/*cached_attrs* are provided from
    _scan_chapters pre-parsing, skips redundant BeautifulSoup parsing.
    """
    cfg = ENGINES[engine]
    if cached_soup is not None and cached_nodes is not None:
        soup = cached_soup
        nodes = cached_nodes
        attrs = cached_attrs if cached_attrs is not None else []
    else:
        soup = BeautifulSoup(html_bytes, "lxml-xml")
        nodes = _get_translatable_nodes(soup)
        attrs = _collect_translatable_attributes(soup, nodes)
    if not nodes and not attrs:
        return html_bytes, 0

    # Extract each element as simplified text + collect attribute values
    texts: list[str] = [_extract_text_with_emphasis(node) for node in nodes]
    attr_texts = [val for _, _, val in attrs]
    char_count = sum(len(t) for t in texts) + sum(len(t) for t in attr_texts)

    # Combine text and attribute values into a single list for batching.
    # Track sources so we can write back to the right place.
    all_texts = texts + attr_texts
    node_sources = [("node", i) for i in range(len(nodes))]
    attr_sources = [("attr", i) for i in range(len(attrs))]
    all_sources = node_sources + attr_sources

    # ── Pre-compute batches ────────────────────────────────────────────────────
    batches: list[list[str]] = []
    source_batches: list[list] = []
    cur_batch: list[str] = []
    cur_sources: list = []
    cur_len = 0

    for text, source in zip(all_texts, all_sources):
        if (
            cur_len + len(text) > cfg.char_limit or len(cur_batch) >= cfg.elem_limit
        ) and cur_batch:
            batches.append(cur_batch)
            source_batches.append(cur_sources)
            cur_batch, cur_sources, cur_len = [], [], 0
        cur_batch.append(text)
        cur_sources.append(source)
        cur_len += len(text)
    if cur_batch:
        batches.append(cur_batch)
        source_batches.append(cur_sources)

    total_batches = len(batches)

    # ── Translate each batch ──────────────────────────────────────────────────
    def translate_batch(batch_texts: list[str]) -> list[str]:
        try:
            result = cfg.translate(
                batch_texts,
                creativity=creativity,
                glossary=glossary,
                extra_prompt=extra_prompt,
            )
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
    translated_sources: list = []
    for i, (batch, src_batch) in enumerate(zip(batches, source_batches)):
        if cfg.delay and i > 0:
            time.sleep(cfg.delay)
        # Update chapter context with batch info for retry messages
        from .engines.base import set_current_chapter_info

        if total_batches > 1:
            set_current_chapter_info(f"batch {i + 1}/{total_batches}")
        translated = translate_batch(batch)
        translated_all.extend(translated)
        translated_sources.extend(src_batch)
        if progress_cb:
            progress_cb(i + 1, total_batches, sum(len(t) for t in batch))

    # ── Write back: separate node and attribute translations ────────────────
    node_translations: dict[int, str] = dict()
    attr_translations: dict[int, str] = dict()
    for trans, src in zip(translated_all, translated_sources):
        kind, idx = src
        if kind == "node":
            node_translations[idx] = trans
        elif kind == "attr":
            attr_translations[idx] = trans

    for node_idx, translated in node_translations.items():
        node = nodes[node_idx]
        cleaned = _clean_translated(translated)
        # Preserve non-text child elements (img, br, span, etc.)
        # that are not emphasis tags — they would be lost on clear().
        preserved_children = [
            child
            for child in node.children
            if isinstance(child, Tag) and child.name not in EMPHASIS_TAGS
        ]
        node.clear()
        if "<" in cleaned:
            # HTML-escape text segments so literal <, >, & don't break XML parsing
            parts = _EMPHASIS_RE.split(cleaned)
            for j in range(0, len(parts), 2):
                parts[j] = html_lib.escape(parts[j], quote=False)
            escaped = "".join(parts)
            frag = BeautifulSoup(f"<x>{escaped}</x>", "lxml-xml").find("x")
            assert frag is not None
            for child in list(frag.children):
                node.append(child)
        else:
            node.append(NavigableString(cleaned))
        # Re-append preserved children (e.g. img tags whose alt was translated)
        for child in preserved_children:
            node.append(child)

    # ── Write back: attribute values ────────────────────────────────────────
    for attr_idx, translated in attr_translations.items():
        tag, attr_name, _ = attrs[attr_idx]
        tag[attr_name] = translated

    return soup.encode("utf-8"), char_count
