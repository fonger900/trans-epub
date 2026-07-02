"""HTML translation logic."""

import re
import time

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


def translate_html(
    html_bytes: bytes,
    engine: str,
    creativity: float | None = None,
) -> tuple[bytes, int]:
    """Translate all translatable text nodes in *html_bytes*.

    Returns ``(translated_html_bytes, total_char_count)``.
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
    translated_all: list[str] = []
    batch: list[str] = []
    batch_len = 0

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

    for text in texts:
        if (
            batch_len + len(text) > cfg.char_limit or len(batch) >= cfg.elem_limit
        ) and batch:
            if cfg.delay:
                time.sleep(cfg.delay)
            translated_all.extend(translate_batch(batch))
            batch, batch_len = [], 0
        batch.append(text)
        batch_len += len(text)

    if batch:
        if cfg.delay:
            time.sleep(cfg.delay)
        translated_all.extend(translate_batch(batch))

    for (child, prefix, core, suffix), translated in zip(text_nodes, translated_all):
        child.replace_with(f"{prefix}{translated}{suffix}")

    return soup.encode("utf-8"), char_count
