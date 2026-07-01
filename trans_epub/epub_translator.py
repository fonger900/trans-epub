"""Top-level EPUB translation orchestration."""

import json
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from ebooklib import epub, ITEM_DOCUMENT
from rich.console import Console
from rich.progress import (
    BarColumn,
    MofNCompleteColumn,
    Progress,
    ProgressColumn,
    SpinnerColumn,
    Task,
    TaskID,
    TextColumn,
    TimeElapsedColumn,
    TimeRemainingColumn,
)
from rich.text import Text

from .html_translator import translate_html
from .toc import translate_toc_and_nav

console = Console()


class _DoneOrSpinner(ProgressColumn):
    """Shows a spinner while running, ✓ when the task is complete."""

    def __init__(self):
        super().__init__()
        self._spinner = SpinnerColumn()

    def render(self, task: Task) -> Text:
        if task.finished:
            return Text("✓", style="bold green")
        # delegate to SpinnerColumn for the animated spinner
        return self._spinner.render(task)


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

    translate_toc_and_nav(book, engine, creativity=creativity)

    # Items that will actually be translated (not skipped)
    work_items = [
        (i, item)
        for i, item in enumerate(items, 1)
        if not only_chapters or i in only_chapters
    ]
    work_total = len(work_items)

    total_chars = 0
    total_chars_lock = threading.Lock()
    cache_lock = threading.Lock()

    # ── Progress UI ────────────────────────────────────────────────────────────
    progress = Progress(
        _DoneOrSpinner(),
        TextColumn("{task.description}"),
        BarColumn(bar_width=None),
        MofNCompleteColumn(),
        TimeElapsedColumn(),
        TimeRemainingColumn(),
        console=console,
        expand=True,
    )

    overall_task: TaskID = progress.add_task(
        "[bold green]Overall", total=work_total
    )

    # Per-worker rows — one per thread, shown only while active
    worker_tasks: list[TaskID] = [
        progress.add_task("", total=1, visible=False)
        for _ in range(threads)
    ]
    worker_lock = threading.Lock()
    free_workers: list[int] = list(range(threads))

    # ── Chapter processor ──────────────────────────────────────────────────────
    def process_chapter(i: int, item) -> None:
        nonlocal total_chars
        name = item.get_name()

        with cache_lock:
            in_cache = name in cache
            cached_content = cache.get(name) if in_cache else None

        if in_cache:
            item.set_content(cached_content.encode("utf-8"))
            progress.advance(overall_task)
            return

        # Claim a worker slot
        with worker_lock:
            wid = free_workers.pop(0)

        progress.update(
            worker_tasks[wid],
            description=f"  [cyan]item {i}[/cyan]",
            completed=0,
            total=1,
            visible=True,
        )

        original = item.get_content()
        try:
            translated, chars = translate_html(original, engine, creativity=creativity)
        except Exception as e:
            progress.update(worker_tasks[wid], visible=False)
            with worker_lock:
                free_workers.append(wid)
            progress.advance(overall_task)
            raise RuntimeError(f"{name}: {e}") from e

        with total_chars_lock:
            total_chars += chars

        with cache_lock:
            cache[name] = translated.decode("utf-8")
            cache_path.write_text(json.dumps(cache, ensure_ascii=False))

        item.set_content(translated)

        progress.update(worker_tasks[wid], completed=1, visible=False)
        with worker_lock:
            free_workers.append(wid)
        progress.advance(overall_task)

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
    if not only_chapters and not failed:
        cache_path.unlink(missing_ok=True)

    if failed:
        console.print(
            f"\n[bold red]{len(failed)} item(s) failed[/bold red] "
            "(re-run to retry):"
        )
        for name, e in failed:
            console.print(f"  [red]•[/red] {name}: {e}")

    console.print(
        f"[bold green]✓ Done[/bold green] → {output_path}  "
        f"([dim]{total_chars:,} chars translated[/dim])"
    )
