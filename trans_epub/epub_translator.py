"""Top-level EPUB translation orchestration."""

from __future__ import annotations

import io
import json
import os
import sys
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

from .config import Glossary, load_glossary
from .html_translator import count_translatable_chars, translate_html
from .toc import rebuild_toc_links, translate_toc_and_nav

console = Console()

_MAX_NAME_LEN = 30


def _short_name(name: str) -> str:
    """Shorten an item path for display, e.g. ``OEBPS/Text/ch01.xhtml`` → ``ch01.xhtml``."""
    basename = os.path.basename(name)
    if len(basename) > _MAX_NAME_LEN:
        return "…" + basename[-(_MAX_NAME_LEN - 1) :]
    return basename


def _repack_epub(path: str) -> None:
    """Rewrite the epub zip in-place to fix CRC mismatches from ebooklib."""
    original = Path(path).read_bytes()
    buf = io.BytesIO()
    with (
        zipfile.ZipFile(io.BytesIO(original), "r") as src,
        zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as dst,
    ):
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


# ── Helpers ───────────────────────────────────────────────────────────────────


def _count_chars(
    work_items: list[tuple[int, object]],
    cache: dict[str, str],
    fresh: bool,
) -> tuple[int, int, int]:
    """Count total, cached, and pending translatable characters."""
    total = cached = pending = 0
    for _i, item in work_items:
        chars = count_translatable_chars(item.get_content())
        total += chars
        if item.get_name() in cache and not fresh:
            cached += chars
        else:
            pending += chars
    return total, cached, pending


def _print_book_info(
    total: int, engine: str, threads: int,
    total_chars: int, cached_chars: int, pending_chars: int,
) -> None:
    """Print book summary and cost estimate."""
    console.print(
        f"[bold]Book:[/bold] {total} items  "
        f"[bold]Engine:[/bold] {engine}  "
        f"[bold]Threads:[/bold] {threads}"
    )
    console.print(
        f"[bold]Total:[/bold] {total_chars:,} chars  "
        f"[bold]Cached:[/bold] {cached_chars:,} chars  "
        f"[bold]Pending:[/bold] {pending_chars:,} chars"
    )
    if engine == "gemini" and pending_chars > 0:
        from .engines.gemini import estimate_gemini_cost

        est = estimate_gemini_cost(pending_chars)
        if est > 0:
            console.print(f"[bold]Est. cost:[/bold] ${est:.4f}")
        else:
            console.print("[bold]Est. cost:[/bold] [green]free[/green]")


def _confirm_proceed(cached_chars: int, fresh: bool) -> bool:
    """Prompt user to confirm. Returns True to proceed, False to abort."""
    if not sys.stdin.isatty():
        return True
    if not fresh:
        console.print(
            f"\n[bold yellow]Use cache for {cached_chars:,} chars?[/bold yellow]"
        )
    try:
        choice = input("\nProceed? [Y/n] ").strip().lower()
        if choice and choice not in ("y", "yes"):
            console.print("[yellow]Aborted[/yellow]")
            return False
    except EOFError:
        console.print("[yellow]Aborted[/yellow]")
        return False
    return True


def _setup_progress(
    threads: int,
) -> tuple[Progress, TaskID, TaskID, list[TaskID], threading.Lock, list[int]]:
    """Create progress bar and worker tracking."""
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
    toc_task = progress.add_task("[yellow]Translating TOC", total=1)
    overall_task = progress.add_task("[bold green]Overall", total=0)
    worker_tasks = [
        progress.add_task("", total=1, visible=False) for _ in range(threads)
    ]
    return progress, toc_task, overall_task, worker_tasks, threading.Lock(), list(range(threads))


def _print_results(
    output_path: str, engine: str, total_chars: int, cached_chars: int,
    failed: list[tuple[str, str]],
) -> None:
    """Print final summary, cost, and failure details."""
    if engine == "gemini":
        from .engines.gemini import actual_gemini_cost, get_gemini_usage

        cost = actual_gemini_cost()
        prompt_tok, output_tok = get_gemini_usage()
        if cost > 0:
            console.print(
                f"[bold]Cost:[/bold] ${cost:.4f}  "
                f"([dim]{prompt_tok:,} in + {output_tok:,} out = "
                f"{prompt_tok + output_tok:,} tokens[/dim])"
            )
        elif prompt_tok + output_tok > 0:
            console.print(
                f"[bold]Cost:[/bold] [green]free[/green]  "
                f"([dim]{prompt_tok:,} in + {output_tok:,} out = "
                f"{prompt_tok + output_tok:,} tokens[/dim])"
            )

    console.print(
        f"[bold green]✓ Done[/bold green] → {output_path}  "
        f"([dim]{total_chars:,} chars translated ({total_chars // 4:,} tokens)[/dim], "
        f"[dim]{cached_chars:,} cached[/dim])"
    )

    if failed:
        console.print(
            f"\n[bold red]{len(failed)} item(s) failed[/bold red] (re-run to retry):"
        )
        for name, e in failed:
            console.print(f"  [red]•[/red] {name}: {e}")
        console.print(
            "\n[dim]Tips:[/dim]"
            " If quota exceeded: reduce creativity, increase delay between requests,"
            " or check API quota limits."
        )

    if any("quota" in e.lower() for _, e in failed) or any(
        "limit" in e.lower() for _, e in failed
    ):
        console.print(
            "\n[dim]Note: If API quota exceeded, try --fresh to start fresh or "
            "reduce --creativity to lower token usage."
        )


# ── Main ──────────────────────────────────────────────────────────────────────


def translate_epub(
    input_path: str,
    output_path: str,
    engine: str,
    only_chapters: set[int] | None = None,
    list_only: bool = False,
    threads: int = 4,
    creativity: float | None = None,
    glossary_path: str | None = None,
    fresh: bool = False,
    extra_prompt: str = "",
) -> None:
    """Translate *input_path* from English to Vietnamese and write *output_path*."""
    cache_path = Path(output_path + ".cache.json")
    cache: dict[str, str] = (
        json.loads(cache_path.read_text()) if cache_path.exists() and not fresh else {}
    )

    if engine == "gemini":
        from .engines.gemini import reset_gemini_usage

        reset_gemini_usage()

    glossary: Glossary | None = None
    if glossary_path:
        glossary_file = Path(glossary_path)
        if not glossary_file.exists():
            console.print(f"[red]Glossary not found:[/red] {glossary_path}")
            return
        glossary = load_glossary(glossary_file)
    else:
        glossary = load_glossary()

    if glossary:
        console.print(
            f"[dim]Glossary:[/dim] {len(glossary.characters)} characters, "
            f"{len(glossary.terms)} terms"
        )

    book = epub.read_epub(input_path)
    if not any(isinstance(item, epub.EpubNav) for item in book.items):
        book.add_item(epub.EpubNav())

    items = get_spine_items(book)

    if list_only:
        console.print(f"[bold]{'No.':<5}[/bold] File")
        console.print("-" * 60)
        for i, item in enumerate(items, 1):
            console.print(f"{i:<5} {item.get_name()}")
        return

    work_items = [
        (i, item)
        for i, item in enumerate(items, 1)
        if not only_chapters or i in only_chapters
    ]
    total_chars, cached_chars, pending_chars = _count_chars(work_items, cache, fresh)
    _print_book_info(len(items), engine, threads, total_chars, cached_chars, pending_chars)

    if not _confirm_proceed(cached_chars, fresh):
        return

    # Reset counters (pre-scan values were for display only)
    total_chars = 0
    cached_chars = 0
    total_chars_lock = threading.Lock()
    cache_lock = threading.Lock()

    progress, toc_task, overall_task, worker_tasks, worker_lock, free_workers = (
        _setup_progress(threads)
    )
    progress.update(overall_task, total=len(work_items))

    def process_chapter(i: int, item) -> None:
        nonlocal total_chars, cached_chars
        name = item.get_name()

        with cache_lock:
            in_cache = name in cache
            cached_content = cache.get(name) if in_cache else None

        if in_cache:
            assert cached_content is not None
            item.set_content(cached_content.encode("utf-8"))
            progress.update(overall_task, advance=1)
            with total_chars_lock:
                total_chars += count_translatable_chars(item.get_content())
                cached_chars += count_translatable_chars(item.get_content())
            return

        with worker_lock:
            wid = free_workers.pop(0)

        fname = _short_name(name)
        progress.update(
            worker_tasks[wid],
            description=f"  [cyan]{fname}[/cyan]",
            completed=0, total=1, visible=True,
        )

        def on_progress(batch_num: int, total_batches: int, batch_chars: int) -> None:
            nonlocal total_chars
            progress.update(
                worker_tasks[wid], description=f"  [cyan]{fname}[/cyan]",
                completed=batch_num, total=total_batches,
            )
            with total_chars_lock:
                total_chars += batch_chars

        try:
            translated, _ = translate_html(
                item.get_content(), engine, creativity=creativity,
                progress_cb=on_progress, glossary=glossary, extra_prompt=extra_prompt,
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

    def restore_skipped(i: int, item) -> None:
        with cache_lock:
            cached_content = cache.get(item.get_name())
        if cached_content:
            item.set_content(cached_content.encode("utf-8"))

    failed: list[tuple[str, str]] = []
    try:
        with progress:
            translate_toc_and_nav(
                book, engine, cache, creativity=creativity,
                glossary=glossary, extra_prompt=extra_prompt,
            )
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
                        except KeyboardInterrupt:
                            raise
                        except Exception as e:
                            failed.append((futures[future], str(e)))
            else:
                for i, item in work_items:
                    try:
                        process_chapter(i, item)
                    except KeyboardInterrupt:
                        raise
                    except Exception as e:
                        failed.append((item.get_name(), str(e)))
                for i, item in enumerate(items, 1):
                    if only_chapters and i not in only_chapters:
                        restore_skipped(i, item)
    except KeyboardInterrupt:
        console.print("\n[yellow]Cancelled by user[/yellow]")
        if threads > 1:
            executor.shutdown(wait=False, cancel_futures=True)
        console.print("[dim]Saving partial progress...[/dim]")

    rebuild_toc_links(book)
    epub.write_epub(output_path, book)
    _repack_epub(output_path)
    cache_path.write_text(json.dumps(cache, ensure_ascii=False))

    _print_results(output_path, engine, total_chars, cached_chars, failed)
