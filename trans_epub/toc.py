"""Table-of-contents and nav-document translation."""

from bs4 import BeautifulSoup
from ebooklib import epub

from .engines import ENGINES
from .html_translator import translate_html


def translate_toc_and_nav(
    book: epub.EpubBook,
    engine: str,
    creativity: float | None = None,
) -> None:
    """Translate TOC link titles and the EPUB nav document in-place."""
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
        translated_titles = ENGINES[engine].translate(titles, creativity=creativity)
        for link, translated in zip(links, translated_titles):
            link.title = translated

    for item in book.get_items():
        if not isinstance(item, epub.EpubNav):
            continue
        content = item.get_content().decode("utf-8")
        soup = BeautifulSoup(content, "html.parser")
        # Flatten anchor text to plain strings before HTML translation
        for anchor in soup.find_all("a"):
            text = anchor.get_text(strip=True)
            if text:
                anchor.string = text
        translated_html, _ = translate_html(
            soup.encode("utf-8"), engine, creativity=creativity
        )
        item.set_content(translated_html)
        break
