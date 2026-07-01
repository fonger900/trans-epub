"""Top-level EPUB translation orchestration."""

import json
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from ebooklib import epub, ITEM_DOCUMENT

from .html_translator import translate_html
from .toc import translate_toc_and_nav


def get_spine_items(book: epub.EpubBook) -> list:
    """Return spine items in spine order, skipping any missing IDs."""
    spine_ids = [idref for idref, _ in book.spine]
    by_id = {item.get_id(): item for item in book.get_items_of_type(ITEM_DOCUMENT)}
    return [by_id[sid] for sid in spine_ids if sid in by_id]


def translate_epub(
    input_path: str,
    output_path: str,
    engine: str,
    only_chapters: set[int] | None = None,
    list_only: bool = False,
    threads: int = 4,
    creativity: float | None = None,
) -> None:
    """Translate *input_path* from English to Vietnamese and write *output_path*."""
    cache_path = Path(output_path + ".cache.json")
    cache: dict[str, str] = (
        json.loads(cache_path.read_text()) if cache_path.exists() else {}
    )

    book = epub.read_epub(input_path)

    # Ensure there is an EpubNav item for EPUB 3 compatibility (fixes ebooklib writer bug)
    if not any(isinstance(item, epub.EpubNav) for item in book.items):
        book.add_item(epub.EpubNav())

    items = get_spine_items(book)
    total = len(items)

    if list_only:
        print(f"{'No.':<5} File")
        print("-" * 60)
        for i, item in enumerate(items, 1):
            print(f"{i:<5} {item.get_name()}")
        return

    print(f"Book has {total} chapter(s). Engine: {engine} (Threads: {threads})\n")

    translate_toc_and_nav(book, engine, creativity=creativity)

    total_chars = 0
    total_chars_lock = threading.Lock()
    cache_lock = threading.Lock()
    print_lock = threading.Lock()

    def safe_print(*args, **kwargs):
        with print_lock:
            print(*args, **kwargs)

    def process_chapter(i: int, item) -> None:
        nonlocal total_chars
        name = item.get_name()

        # Chapter not in the requested set — restore from cache if available
        if only_chapters and i not in only_chapters:
            with cache_lock:
                cached_content = cache.get(name)
            if cached_content:
                item.set_content(cached_content.encode("utf-8"))
            return

        with cache_lock:
            in_cache = name in cache
            cached_content = cache.get(name) if in_cache else None

        if in_cache:
            safe_print(f"  [{i}/{total}] SKIP (cached): {name}")
            item.set_content(cached_content.encode("utf-8"))
            return

        original = item.get_content()
        safe_print(f"  [{i}/{total}] Translating: {name} ({len(original):,} bytes)...")

        try:
            translated, chars = translate_html(original, engine, creativity=creativity)
        except Exception as e:
            safe_print(f"  [{i}/{total}] ERROR translating {name}: {e}")
            raise

        with total_chars_lock:
            total_chars += chars

        with cache_lock:
            cache[name] = translated.decode("utf-8")
            cache_path.write_text(json.dumps(cache, ensure_ascii=False))

        item.set_content(translated)
        safe_print(f"  [{i}/{total}] Done: {name} ({chars:,} chars)")

    if threads > 1:
        with ThreadPoolExecutor(max_workers=threads) as executor:
            futures = {
                executor.submit(process_chapter, i, item): item.get_name()
                for i, item in enumerate(items, 1)
            }
            failed = []
            for future in futures:
                try:
                    future.result()
                except Exception as e:
                    failed.append((futures[future], e))
            if failed:
                print(
                    f"\n{len(failed)} chapter(s) failed "
                    "(others were cached/completed; re-run to retry just these):"
                )
                for name, e in failed:
                    print(f"  - {name}: {e}")
    else:
        for i, item in enumerate(items, 1):
            process_chapter(i, item)

    epub.write_epub(output_path, book)
    if not only_chapters:
        cache_path.unlink(missing_ok=True)
    print(f"\nDone → {output_path}  (translated ~{total_chars:,} chars)")
