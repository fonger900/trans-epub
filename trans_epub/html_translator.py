"""HTML translation logic."""

import re
import time
from typing import Callable

from bs4 import BeautifulSoup

from .engines import ENGINES

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

    def should_preserve(tag) -> bool:
        for current in [tag, *tag.parents]:
            if getattr(current, "name", None) in PRESERVE_TAGS:
                return True
            classes = current.get("class", []) if hasattr(current, "get") else []
            if isinstance(classes, str):
                classes = classes.split()
            if any(cls in PRESERVE_CLASSES for cls in classes):
                return True
        return False

    nodes = [
        tag
        for tag in soup.find_all(TRANSLATE_TAGS)
        if tag.get_text(strip=True)
        and not tag.find(BLOCK_TAGS)
        and not should_preserve(tag)
    ]
    if not nodes:
        return html_bytes, 0

    text_nodes: list[tuple] = []
    texts: list[str] = []

    for node in nodes:
        for child in node.find_all(string=True):
            text = str(child)
            if not text.strip():
                continue
            match = re.match(r"^(\s*)(.*?)(\s*)$", text, flags=re.S)
            if match:
                prefix, core, suffix = match.groups()
            else:
                prefix, core, suffix = "", text, ""
            text_nodes.append((child, prefix, core, suffix))
            texts.append(core)

    if not texts:
        return html_bytes, 0

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
        def collapse_translation(parts: list[str]) -> str:
            return " ".join(part.strip() for part in parts if part.strip())

        def translate_batch(batch_texts: list[str]) -> list[str]:
            result = cfg.translate(batch_texts, creativity=creativity)
            if len(result) == len(batch_texts):
                return result
            if len(batch_texts) == 1:
                return [collapse_translation(result)]
            mid = len(batch_texts) // 2
            return translate_batch(batch_texts[:mid]) + translate_batch(batch_texts[mid:])

        translated_all: list[str] = []
        for i, batch in enumerate(batches):
            if cfg.delay and i > 0:
                time.sleep(cfg.delay)
            translated_all.extend(translate_batch(batch))
            if progress_cb:
                progress_cb(i + 1, total_batches, sum(len(t) for t in batch))

    for (child, prefix, core, suffix), translated in zip(text_nodes, translated_all):
        child.replace_with(f"{prefix}{translated}{suffix}")

    return soup.encode("utf-8"), char_count
