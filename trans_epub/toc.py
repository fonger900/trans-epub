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
    extra_prompt: str = "",
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
                titles,
                creativity=creativity,
                glossary=glossary,
                extra_prompt=extra_prompt,
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
        soup = BeautifulSoup(item.get_content(), "xml")
        # Flatten anchor text to plain strings before HTML translation
        for anchor in soup.find_all("a"):
            text = anchor.get_text(strip=True)
            if text:
                anchor.string = text
        translated_html, _ = translate_html(
            soup.encode("utf-8"),
            engine,
            creativity=creativity,
            glossary=glossary,
            extra_prompt=extra_prompt,
        )
        cache[nav_name] = translated_html.decode("utf-8")
        item.set_content(translated_html)
        break


def _toc_href_to_relative(href: str, toc_dir: str) -> str:
    """Convert a book.toc href (relative to epub root) to a path relative to the TOC page."""
    from posixpath import basename

    if toc_dir and href.startswith(toc_dir):
        return href[len(toc_dir) :]
    return basename(href)


# Filenames that typically appear in the in-book TOC
_TOC_ITEM_PATTERNS = {"_c0", "_ack", "_nts", "_app", "_idx", "_ata", "_ded", "_nt"}


def _is_toc_candidate(href: str) -> bool:
    """Check if an href looks like a chapter/section entry (not front matter)."""
    from posixpath import basename

    bn = basename(href)
    return any(p in bn for p in _TOC_ITEM_PATTERNS)


def rebuild_toc_links(book: epub.EpubBook) -> None:
    """Rebuild <a> tags in the in-book TOC page from book.toc link hrefs."""
    from posixpath import dirname

    toc_entries = []
    for link in book.toc or []:
        if getattr(link, "href", None):
            toc_entries.append(link.href)
        if getattr(link, "content", None):
            for child in link.content:
                if getattr(child, "href", None):
                    toc_entries.append(child.href)

    for item in book.get_items():
        if isinstance(item, epub.EpubNav):
            continue
        if "toc" not in item.get_name().lower():
            continue
        soup = BeautifulSoup(item.get_content(), "xml")
        toc_div = soup.find(attrs={"role": "doc-toc"})  # type: ignore[reportArgumentType]
        if not toc_div:
            continue

        toc_dir = dirname(item.get_name())
        if toc_dir and not toc_dir.endswith("/"):
            toc_dir += "/"

        paragraphs = [
            p
            for p in toc_div.find_all("p")
            if p.get_text(strip=True) and not p.find("a")
        ]

        # Find the offset: first toc_entries entry that is a chapter/section item
        start_idx = 0
        for i, href in enumerate(toc_entries):
            if _is_toc_candidate(href):
                start_idx = i
                break

        matched = toc_entries[start_idx : start_idx + len(paragraphs)]
        for p, href in zip(paragraphs, matched):
            text = p.get_text(strip=True)
            rel_href = _toc_href_to_relative(href, toc_dir)
            a = soup.new_tag("a", href=rel_href)
            a.string = text
            p.clear()
            p.append(a)
        item.set_content(str(soup).encode("utf-8"))
        break
