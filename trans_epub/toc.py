"""Table-of-contents and nav-document translation."""

from __future__ import annotations

import json

from bs4 import BeautifulSoup
from ebooklib import epub

from .config import Glossary
from .engines import ENGINES
from .html_translator import translate_html

_TOC_KEY = "__toc__"


def translate_toc_and_nav(
    book: epub.EpubBook,
    engine: str,
    cache: dict[str, str],
    creativity: float | None = None,
    glossary: Glossary | None = None,
) -> None:
    """Translate TOC link titles and the EPUB nav document in-place.

    Uses *cache* to avoid re-translating the TOC on subsequent runs.
    """
    titles: list[str] = []
    links: list = []

    def walk_links(link_list):
        for link in link_list:
            if getattr(link, "title", None):
                titles.append(link.title)
                links.append(link)
            if getattr(link, "content", None):
                walk_links(link.content)

    walk_links(book.toc or [])

    if titles:
        cached = cache.get(_TOC_KEY)
        if cached:
            try:
                translated_titles = json.loads(cached)
                if len(translated_titles) == len(titles):
                    for link, translated in zip(links, translated_titles):
                        link.title = translated
                    titles = []  # Mark as handled, skip API call
            except (json.JSONDecodeError, TypeError):
                pass

        if titles:  # Not cached — translate via API
            translated_titles = ENGINES[engine].translate(
                titles, creativity=creativity, glossary=glossary
            )
            cache[_TOC_KEY] = json.dumps(translated_titles, ensure_ascii=False)
            for link, translated in zip(links, translated_titles):
                link.title = translated

    for item in book.get_items():
        if not isinstance(item, epub.EpubNav):
            continue
        nav_name = item.get_name()
        if nav_name in cache:
            item.set_content(cache[nav_name].encode("utf-8"))
            break
        content = item.get_content().decode("utf-8")
        soup = BeautifulSoup(content, "html.parser")
        # Flatten anchor text to plain strings before HTML translation
        for anchor in soup.find_all("a"):
            text = anchor.get_text(strip=True)
            if text:
                anchor.string = text
        translated_html, _ = translate_html(
            soup.encode("utf-8"), engine, creativity=creativity, glossary=glossary
        )
        cache[nav_name] = translated_html.decode("utf-8")
        item.set_content(translated_html)
        break
