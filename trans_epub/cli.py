"""Command-line interface for trans-epub."""

import argparse
import os

from .epub_translator import translate_epub


def resolve_engine(engine: str) -> str:
    """Resolve 'auto' to the first engine whose API key is present."""
    if engine != "auto":
        return engine
    if os.environ.get("AZURE_TRANSLATOR_KEY"):
        return "azure"
    if os.environ.get("GEMINI_API_KEY"):
        return "gemini"
    if os.environ.get("DEEPSEEK_API_KEY"):
        return "deepseek"
    raise RuntimeError(
        "No translation API key found. "
        "Set AZURE_TRANSLATOR_KEY, GEMINI_API_KEY, or DEEPSEEK_API_KEY."
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Translate EPUB EN→VI")
    parser.add_argument("input")
    parser.add_argument("output", nargs="?")
    parser.add_argument(
        "--engine",
        "-e",
        choices=["auto", "azure", "gemini", "deepseek"],
        default="auto",
    )
    parser.add_argument("--chapters", "-c", help="e.g. 1,3,5 or 2-6 or 1,3-5,8")
    parser.add_argument("--list", "-l", action="store_true")
    parser.add_argument(
        "--threads",
        "-t",
        type=int,
        default=4,
        help="Number of parallel translation threads",
    )
    parser.add_argument(
        "--creativity",
        type=float,
        help="Model creativity/temperature for Gemini and DeepSeek",
    )
    args = parser.parse_args(argv)

    out = args.output or args.input.replace(".epub", "_vi.epub")

    only: set[int] | None = None
    if args.chapters:
        only = set()
        for part in args.chapters.split(","):
            if "-" in part:
                a, b = part.split("-", 1)
                only.update(range(int(a), int(b) + 1))
            else:
                only.add(int(part))

    engine = resolve_engine(args.engine)
    translate_epub(
        args.input,
        out,
        engine,
        only,
        list_only=args.list,
        threads=args.threads,
        creativity=args.creativity,
    )
    return 0
