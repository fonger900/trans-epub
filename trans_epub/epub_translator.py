"""Top-level EPUB translation orchestration."""

import io
import json
import os
import threading
import zipfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from ebooklib import ITEM_DOCUMENT, epub
from rich.console import Console
from rich.progress import (
    BarColumn,
    MofNCompleteColumn,
    Progress,
    SpinnerColumn,
    TaskID,
    TextColumn,
    TimeElapsedColumn,
    TimeRemainingColumn,
)

from .html_translator import count_translatable_chars, translate_html
from .toc import translate_toc_and_nav

console = Console()

_MAX_NAME_LEN = 30


def _short_name(name: str) -> str:
    """Shorten an item path for display, e.g. ``OEBPS/Text/ch01.xhtml`` → ``ch01.xhtml``."""
    basename = os.path.basename(name)
    if len(basename) > _MAX_NAME_LEN:
        return "…" + basename[-(_MAX_NAME_LEN - 1) :]
    return basename


def _repack_epub(path: str) -> None:
    """Rewrite the epub zip in-place to fix CRC mismatches from ebooklib.

    ebooklib sometimes writes zip entries with incorrect CRC-32 values.
    Re-reading and rewriting every entry through Python's zipfile fixes it.
    The mimetype entry must be first and uncompressed per the EPUB spec.
    """
    original = Path(path).read_bytes()
    buf = io.BytesIO()
    with (
        zipfile.ZipFile(io.BytesIO(original), "r") as src,
        zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as dst,
    ):
        # mimetype must be first and stored uncompressed
        if "mimetype" in src.namelist():
            dst.writestr(
                zipfile.ZipInfo("mimetype"),
                src.read("mimetype"),
                compress_type=zipfile.ZIP_STORED,
            )
        for item in src.infolist():
            if item.filename == "mimetype":
                continue
            dst.writestr(item.filename, src.read(item.filename))
    Path(path).write_bytes(buf.getvalue())


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
        console.print(f"[bold]{'No.':<5}[/bold] File")
        console.print("-" * 60)
        for i, item in enumerate(items, 1):
            console.print(f"{i:<5} {item.get_name()}")
        return

    console.print(
        f"[bold]Book:[/bold] {total} items  "
        f"[bold]Engine:[/bold] {engine}  "
        f"[bold]Threads:[/bold] {threads}"
    )

    # Items that will actually be translated (not skipped)
    work_items = [
        (i, item)
        for i, item in enumerate(items, 1)
        if not only_chapters or i in only_chapters
    ]

    total_chars = 0
    cached_chars = 0
    total_chars_lock = threading.Lock()
    cache_lock = threading.Lock()

    num_work = len(work_items)

    # ── Progress UI (shown immediately so user sees activity during TOC phase) ─
    progress = Progress(
        SpinnerColumn(),
        TextColumn("{task.description}"),
        BarColumn(bar_width=None),
        MofNCompleteColumn(),
        TimeElapsedColumn(),
        TimeRemainingColumn(),
        console=console,
        expand=True,
    )

    toc_task: TaskID = progress.add_task("[yellow]Translating TOC", total=1)
    overall_task: TaskID = progress.add_task("[bold green]Overall", total=num_work)

    # Per-worker rows — one per thread, shown only while active
    worker_tasks: list[TaskID] = [
        progress.add_task("", total=1, visible=False) for _ in range(threads)
    ]
    worker_lock = threading.Lock()
    free_workers: list[int] = list(range(threads))

    # ── Chapter processor ──────────────────────────────────────────────────────
    def process_chapter(i: int, item) -> None:
        nonlocal total_chars, cached_chars
        name = item.get_name()
        fname = _short_name(name)

        with cache_lock:
            in_cache = name in cache
            cached_content = cache.get(name) if in_cache else None

        if in_cache:
            assert cached_content is not None  # Guaranteed by in_cache check
            item.set_content(cached_content.encode("utf-8"))
            progress.update(overall_task, advance=1)
            chars = count_translatable_chars(item.get_content())
            with total_chars_lock:
                total_chars += chars
                cached_chars += chars
            return

        # Claim a worker slot
        with worker_lock:
            wid = free_workers.pop(0)

        progress.update(
            worker_tasks[wid],
            description=f"  [cyan]{fname}[/cyan]",
            completed=0,
            total=1,
            visible=True,
        )

        # Overall bar advances 1 per completed chapter; per-chapter bar
        # shows batch-level detail for in-progress work.

        def on_progress(batch_num: int, total_batches: int, batch_chars: int) -> None:
            nonlocal total_chars
            progress.update(
                worker_tasks[wid],
                description=(
                    f"  [cyan]{fname}[/cyan] [dim]{batch_num}/{total_batches}[/dim]"
                ),
                completed=batch_num,
                total=total_batches,
            )
            with total_chars_lock:
                total_chars += batch_chars

        original = item.get_content()
        try:
            translated, chars = translate_html(
                original, engine, creativity=creativity, progress_cb=on_progress
            )
        except Exception as e:
            progress.update(worker_tasks[wid], visible=False)
            with worker_lock:
                free_workers.append(wid)
            raise RuntimeError(f"{name}: {e}") from e

        progress.update(overall_task, advance=1)

        with cache_lock:
            cache[name] = translated.decode("utf-8")
            cache_path.write_text(json.dumps(cache, ensure_ascii=False))

        item.set_content(translated)

        progress.update(worker_tasks[wid], visible=False)
        with worker_lock:
            free_workers.append(wid)

    # ── Load cached content for skipped items ──────────────────────────────────
    def restore_skipped(i: int, item) -> None:
        name = item.get_name()
        with cache_lock:
            cached_content = cache.get(name)
        if cached_content:
            item.set_content(cached_content.encode("utf-8"))

    # ── Execute ────────────────────────────────────────────────────────────────
    failed: list[tuple[str, str]] = []

    with progress:
        translate_toc_and_nav(book, engine, cache, creativity=creativity)
        cache_path.write_text(json.dumps(cache, ensure_ascii=False))
        progress.update(toc_task, advance=1, visible=False)

        if threads > 1:
            with ThreadPoolExecutor(max_workers=threads) as executor:
                futures = {
                    executor.submit(process_chapter, i, item): item.get_name()
                    for i, item in work_items
                }
                for i, item in enumerate(items, 1):
                    if only_chapters and i not in only_chapters:
                        restore_skipped(i, item)

                for future in futures:
                    try:
                        future.result()
                    except Exception as e:
                        failed.append((futures[future], str(e)))
        else:
            for i, item in work_items:
                try:
                    process_chapter(i, item)
                except Exception as e:
                    failed.append((item.get_name(), str(e)))
            for i, item in enumerate(items, 1):
                if only_chapters and i not in only_chapters:
                    restore_skipped(i, item)

    # Always write — preserve whatever was translated even on partial failure
    epub.write_epub(output_path, book)
    _repack_epub(output_path)
    if not only_chapters and not failed:
        cache_path.unlink(missing_ok=True)

    if failed:
        console.print(
            f"\n[bold red]{len(failed)} item(s) failed[/bold red] (re-run to retry):"
        )
        for name, e in failed:
            console.print(f"  [red]•[/red] {name}: {e}")

    console.print(
        f"[bold green]✓ Done[/bold green] → {output_path}  "
        f"([dim]{total_chars:,} chars translated[/dim], "
        f"[dim]{cached_chars:,} cached[/dim])"
    )
