"""Top-level EPUB translation orchestration."""

from __future__ import annotations

import hashlib
import io
import json
import os
import signal
import sys
import threading
import zipfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

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

from .config import Glossary, load_glossary, validate_glossary, scan_glossary_matches
from .engines.base import (
    set_verbose,
    set_current_chapter,
    set_current_chapter_info,
    reset_cancel_event,
    request_cancel,
)
from .html_translator import translate_html
from .toc import rebuild_toc_links, translate_toc_and_nav

console = Console()

_MAX_NAME_LEN = 30
_CACHE_HASH_KEY = "__epub_hash__"


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


def get_spine_items(book: epub.EpubBook) -> list[epub.EpubItem]:
    """Return spine items in spine order, skipping any missing IDs."""
    spine_ids = [idref for idref, _ in book.spine]
    by_id = {item.get_id(): item for item in book.get_items_of_type(ITEM_DOCUMENT)}
    return [by_id[sid] for sid in spine_ids if sid in by_id]


# ── Helpers ───────────────────────────────────────────────────────────────────


def _load_cache(
    cache_path: Path, input_path: str, fresh: bool
) -> dict[str, str]:
    """Load and validate the translation cache.

    Validates JSON integrity and checks that the cache matches the current EPUB.
    Returns an empty dict if the cache is missing, corrupted, or fresh is True.
    """
    if fresh or not cache_path.exists():
        return {}

    try:
        data = json.loads(cache_path.read_text())
    except json.JSONDecodeError:
        console.print(
            "[yellow]Warning:[/yellow] Cache file is corrupted, starting fresh"
        )
        return {}

    if not isinstance(data, dict):
        console.print("[yellow]Warning:[/yellow] Invalid cache format, starting fresh")
        return {}

    # Check EPUB hash to detect changed source files
    epub_path = Path(input_path)
    epub_hash = hashlib.md5(epub_path.read_bytes()).hexdigest() if epub_path.exists() else None
    cached_hash = data.pop(_CACHE_HASH_KEY, None)
    if cached_hash and cached_hash != epub_hash:
        console.print(
            "[yellow]Warning:[/yellow] EPUB has changed since cache was created. "
            "Use [bold]--fresh[/bold] to re-translate from scratch."
        )
        # Keep using the cache but warn — user may still want partial reuse

    return data


def _save_cache(cache_path: Path, cache: dict[str, str], input_path: str) -> None:
    """Save cache with EPUB integrity hash. Uses atomic write to prevent
    corruption from crashes mid-save."""
    epub_path = Path(input_path)
    if epub_path.exists():
        epub_hash = hashlib.md5(epub_path.read_bytes()).hexdigest()
        cache[_CACHE_HASH_KEY] = epub_hash
    tmp_path = cache_path.with_suffix(cache_path.suffix + ".tmp")
    tmp_path.write_text(json.dumps(cache, ensure_ascii=False))
    os.replace(tmp_path, cache_path)
    cache.pop(_CACHE_HASH_KEY, None)



def _scan_chapters(
    work_items: list[tuple[int, epub.EpubItem]], cache: dict[str, str], fresh: bool
) -> list[dict[str, Any]]:
    """Scan chapters to pre-calculate metrics and cache statuses.

    Also pre-parses each chapter's HTML and caches the parsed soup/nodes/attrs
    so translate_html can skip re-parsing later.
    """
    from bs4 import BeautifulSoup

    from .html_translator import (
        _collect_translatable_attributes,
        _extract_text_with_emphasis,
        _get_translatable_nodes,
    )

    jobs = []
    for i, item in work_items:
        name = item.get_name()
        content = item.get_content()

        # Parse once; cache the parsed data for later reuse by translate_html
        soup = BeautifulSoup(content, "lxml-xml")
        nodes = _get_translatable_nodes(soup)
        attrs = _collect_translatable_attributes(soup, nodes)
        char_count = sum(len(_extract_text_with_emphasis(n)) for n in nodes)
        char_count += sum(len(val) for _, _, val in attrs)

        is_cached = name in cache and not fresh

        jobs.append(
            {
                "index": i,
                "item": item,
                "name": name,
                "char_count": char_count,
                "is_cached": is_cached,
                "cached_content": cache.get(name) if is_cached else None,
                "_soup": soup,
                "_nodes": nodes,
                "_attrs": attrs,
            }
        )
    return jobs


def _print_book_info(
    total_items: int,
    engine: str,
    threads: int,
    jobs: list[dict[str, Any]],
    glossary: Glossary | None = None,
    extra_prompt: str = "",
) -> None:
    """Print book summary metrics and accurate cost layout[cite: 2]."""
    total_chars = sum(j["char_count"] for j in jobs)
    cached_chars = sum(j["char_count"] for j in jobs if j["is_cached"])
    pending_chapters = [j["char_count"] for j in jobs if not j["is_cached"]]
    total_pending = sum(pending_chapters)

    console.print(
        f"[bold]Book:[/bold] {total_items} items  "
        f"[bold]Engine:[/bold] {engine}  "
        f"[bold]Threads:[/bold] {threads}"
    )
    console.print(
        f"[bold]Total:[/bold] {total_chars:,} chars  "
        f"[bold]Cached:[/bold] {cached_chars:,} chars  "
        f"[bold]Pending:[/bold] {total_pending:,} chars"
    )

    if engine == "gemini" and total_pending > 0:
        from .engines.base import build_prompt
        from .engines.gemini import estimate_gemini_cost

        prompt_chars = len(build_prompt(glossary, extra_prompt))
        est = estimate_gemini_cost(pending_chapters, prompt_chars=prompt_chars)
        if est > 0:
            console.print(f"[bold]Est. cost:[/bold] ${est:.4f}")
        else:
            console.print("[bold]Est. cost:[/bold] [green]free[/green]")

        # Warn about free tier RPM limits for lite models
        import os

        model = os.environ.get("GEMINI_MODEL") or ""
        if "lite" in model.lower():
            batch_count = sum(
                max(1, (c + 10_000 - 1) // 10_000)
                for c in pending_chapters if c > 0
            )
            if batch_count > 15:
                est_min = batch_count / 15
                console.print(
                    f"[yellow]Free tier:[/yellow] {batch_count} API calls"
                    f" at 15 RPM = ~{est_min:.0f} min minimum"
                )


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
    except (EOFError, KeyboardInterrupt):
        console.print("\n[yellow]Aborted[/yellow]")
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
    return (
        progress,
        toc_task,
        overall_task,
        worker_tasks,
        threading.Lock(),
        list(range(threads)),
    )


def _print_results(
    output_path: str,
    engine: str,
    total_chars: int,
    cached_chars: int,
    failed: list[tuple[str, str]],
) -> None:
    """Print final summary, cost, and failure details[cite: 3]."""
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
        # Categorize failures for targeted recovery advice
        quota_fails = []
        network_fails = []
        parse_fails = []
        other_fails = []
        for name, err in failed:
            err_lower = err.lower()
            if any(kw in err_lower for kw in ("quota", "limit exceeded", "daily limit",
                    "insufficient quota", "billing", "payment required", "rate limit")):
                quota_fails.append((name, err))
            elif any(kw in err_lower for kw in ("timeout", "connection", "network",
                    "reset by peer", "refused")):
                network_fails.append((name, err))
            elif "parse" in err_lower or "json" in err_lower:
                parse_fails.append((name, err))
            else:
                other_fails.append((name, err))

        console.print(
            f"\n[bold red]{len(failed)} item(s) failed[/bold red]"
            f" ([dim]re-run to retry[/dim]):"
        )

        def _show_group(label, items, advice):
            if not items:
                return
            console.print(f"\n  [bold]{label}[/bold] ({len(items)}):")
            for name, err in items[:5]:
                short = _short_name(name)
                console.print(f"    [red]•[/red] {short}: {err[:120]}")
            if len(items) > 5:
                console.print(f"    [dim]... and {len(items) - 5} more[/dim]")
            console.print(f"  [dim]Fix: {advice}[/dim]")

        _show_group(
            "Quota / rate limit", quota_fails,
            "Check API billing, reduce --creativity, wait before retrying.",
        )
        _show_group(
            "Network / timeout", network_fails,
            "Check internet connection. Set GEMINI_TIMEOUT higher or reduce --threads.",
        )
        _show_group(
            "Parse / JSON error", parse_fails,
            "API returned malformed response. Try different --creativity or engine.",
        )
        _show_group(
            "Other", other_fails,
            "Check error details above. Run with --verbose for request-level logs.",
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
    dry_run: bool = False,
    verbose: bool = False,
    rpm: int | None = None,
    chapter_timeout: int = 600,
    extra_prompt: str = "",
) -> None:
    """Translate *input_path* from English to Vietnamese and write *output_path*."""
    set_verbose(verbose)
    reset_cancel_event()
    if rpm is not None:
        from .engines.base import ENGINES, RateLimiter

        if engine in ENGINES:
            ENGINES[engine].limiter = RateLimiter(rpm=rpm)
            if verbose:
                console.print(f"[dim]Rate limit: {rpm} RPM[/dim]")
    cache_path = Path(output_path + ".cache.json")
    cache: dict[str, str] = _load_cache(cache_path, input_path, fresh)

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
        warnings = validate_glossary(glossary)
        for w in warnings:
            console.print(f"  [yellow]! {w}[/yellow]")

    book = epub.read_epub(input_path)
    if not any(isinstance(item, epub.EpubNav) for item in book.items):
        book.add_item(epub.EpubNav())

    items = get_spine_items(book)

    if list_only:
        console.print("[bold]No.   Chars  File[/bold]")
        console.print("-" * 60)
        work_items = [(i, item) for i, item in enumerate(items, 1)]
        jobs = _scan_chapters(work_items, dict(), False)
        total_chars = 0
        for job in jobs:
            console.print(
                str(job["index"]).ljust(5) + " "
                + str(job["char_count"]).rjust(10) + "  "
                + job["name"]
            )
            total_chars += job["char_count"]
        console.print(
            "\n[bold]Total:[/bold] " + format(total_chars, ",") + " chars"
        )
        return

    work_items = [
        (i, item)
        for i, item in enumerate(items, 1)
        if not only_chapters or i in only_chapters
    ]

    # Compile jobs in a single pass, sort by size descending
    # so large chapters start first and run in parallel from the start.
    jobs = _scan_chapters(work_items, cache, fresh)
    jobs.sort(key=lambda j: j["char_count"], reverse=True)
    _print_book_info(
        len(items), engine, threads, jobs, glossary=glossary, extra_prompt=extra_prompt
    )

    if dry_run:
        # Show glossary match stats if glossary is loaded
        if glossary and not glossary.is_empty():
            # Extract plain text from each chapter for scanning
            from bs4 import BeautifulSoup

            chapter_texts = []
            for job in jobs:
                soup = BeautifulSoup(job["item"].get_content(), "xml")
                chapter_texts.append(soup.get_text())

            matches = scan_glossary_matches(glossary, chapter_texts)
            if matches:
                console.print("\n[bold]Glossary match stats:[/bold]")
                found_any = False
                for key, count in sorted(matches.items()):
                    label = key.removeprefix("[character] ")
                    is_char = key.startswith("[character] ")
                    tag = "[character]" if is_char else "[term]"
                    if count > 0:
                        console.print(
                            f"  [green]✓[/green] {tag} {label}: "
                            f"found {count} time(s)"
                        )
                        found_any = True
                    else:
                        console.print(
                            f"  [yellow]✗[/yellow] {tag} {label}: "
                            f"[dim]not found in text[/dim]"
                        )
                if not found_any:
                    console.print(
                        "  [dim]No glossary terms found in selected chapters.[/dim]"
                    )

        console.print(
            "\n[bold green]Dry run complete[/bold green]"
            " — no translation performed."
        )
        console.print(
            "[dim]Run without [bold]--dry-run[/bold]"
            " to start translation.[/dim]"
        )
        return

    cached_chars = sum(j["char_count"] for j in jobs if j["is_cached"])
    if not _confirm_proceed(cached_chars, fresh):
        return

    # Reset structural tracking counters
    total_chars = 0
    cached_chars = 0
    total_chars_lock = threading.Lock()
    cache_lock = threading.Lock()

    progress, toc_task, overall_task, worker_tasks, worker_lock, free_workers = (
        _setup_progress(threads)
    )
    progress.update(overall_task, total=len(jobs))

    def process_chapter(job: dict[str, Any]) -> None:
        nonlocal total_chars, cached_chars
        item = job["item"]
        name = job["name"]

        if job["is_cached"]:
            item.set_content(job["cached_content"].encode("utf-8"))
            progress.update(overall_task, advance=1)
            with total_chars_lock:
                total_chars += job["char_count"]
                cached_chars += job["char_count"]
            return

        with worker_lock:
            wid = free_workers.pop(0)

        fname = _short_name(name)
        progress.update(
            worker_tasks[wid],
            description=f"  [cyan]{fname}[/cyan]",
            completed=0,
            total=1,
            visible=True,
        )

        def on_progress(batch_num: int, total_batches: int, batch_chars: int) -> None:
            nonlocal total_chars
            progress.update(
                worker_tasks[wid],
                description=f"  [cyan]{fname}[/cyan]",
                completed=batch_num,
                total=total_batches,
            )
            with total_chars_lock:
                total_chars += batch_chars

        try:
            set_current_chapter(_short_name(name))
            translated, _ = translate_html(
                item.get_content(),
                engine,
                creativity=creativity,
                progress_cb=on_progress,
                glossary=glossary,
                extra_prompt=extra_prompt,
                cached_soup=job.get("_soup"),
                cached_nodes=job.get("_nodes"),
                cached_attrs=job.get("_attrs"),
            )
        except Exception as e:
            progress.update(worker_tasks[wid], visible=False)
            with worker_lock:
                free_workers.append(wid)
            raise RuntimeError(f"{name}: {e}") from e

        progress.update(overall_task, advance=1)
        with cache_lock:
            cache[name] = translated.decode("utf-8")
            _save_cache(cache_path, cache, input_path)
        item.set_content(translated)
        progress.update(worker_tasks[wid], visible=False)
        with worker_lock:
            free_workers.append(wid)

    def restore_skipped(_i: int, item: epub.EpubItem) -> None:
        with cache_lock:
            cached_content = cache.get(item.get_name())
        if cached_content:
            item.set_content(cached_content.encode("utf-8"))

    failed: list[tuple[str, str]] = []
    executor: ThreadPoolExecutor | None = None
    try:
        with progress:
            set_current_chapter("TOC")
            translate_toc_and_nav(
                book,
                engine,
                cache,
                creativity=creativity,
                glossary=glossary,
                extra_prompt=extra_prompt,
            )
            _save_cache(cache_path, cache, input_path)
            progress.update(toc_task, advance=1, visible=False)

            if threads > 1:
                executor = ThreadPoolExecutor(max_workers=threads)
                future_map = {
                    executor.submit(process_chapter, job): job["name"]
                    for job in jobs
                }
                for i, item in enumerate(items, 1):
                    if only_chapters and i not in only_chapters:
                        restore_skipped(i, item)
                try:
                    for future in as_completed(future_map, timeout=chapter_timeout):
                        try:
                            future.result()
                        except KeyboardInterrupt:
                            raise
                        except Exception as e:
                            failed.append((future_map[future], str(e)))
                except TimeoutError:
                    for future, name in future_map.items():
                        if not future.done():
                            future.cancel()
                            failed.append((name, f"timed out after {chapter_timeout}s"))
            else:
                single_executor = ThreadPoolExecutor(max_workers=1)
                for job in jobs:
                    try:
                        single_executor.submit(
                            process_chapter, job
                        ).result(timeout=chapter_timeout)
                    except KeyboardInterrupt:
                        raise
                    except TimeoutError:
                        failed.append((job["name"], f"timed out after {chapter_timeout}s"))
                    except Exception as e:
                        failed.append((job["name"], str(e)))
                for i, item in enumerate(items, 1):
                    if only_chapters and i not in only_chapters:
                        restore_skipped(i, item)
    except KeyboardInterrupt:
        console.print("\n[yellow]Cancelled by user[/yellow]")
        request_cancel()
        # Suppress subsequent Ctrl+C during cleanup to prevent
        # ThreadPoolExecutor atexit traceback on shutdown.
        signal.signal(signal.SIGINT, lambda *_: None)
        if threads > 1 and executor is not None:
            executor.shutdown(wait=False, cancel_futures=True)
        console.print("[dim]Saving partial progress...[/dim]")

    rebuild_toc_links(book)
    epub.write_epub(output_path, book)
    _repack_epub(output_path)
    _save_cache(cache_path, cache, input_path)

    _print_results(output_path, engine, total_chars, cached_chars, failed)
