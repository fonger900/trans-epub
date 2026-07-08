"""Command-line interface for trans-epub."""

import argparse
import os
from pathlib import Path

from dotenv import load_dotenv

from .epub_translator import translate_epub

try:
    from importlib.metadata import PackageNotFoundError, version
except ImportError:
    from importlib_metadata import PackageNotFoundError, version

try:
    __version__ = version("trans-epub")
except PackageNotFoundError:
    __version__ = "unknown"


def resolve_engine(engine: str) -> str:
    """Resolve 'auto' to the first engine whose API key is present."""
    if engine != "auto":
        return engine

    # Check environment variables
    if os.environ.get("AZURE_TRANSLATOR_KEY"):
        return "azure"
    if os.environ.get("GEMINI_API_KEY"):
        return "gemini"
    if os.environ.get("DEEPSEEK_API_KEY"):
        return "deepseek"
    if os.environ.get("DASHSCOPE_API_KEY"):
        return "alibaba"
    if os.environ.get("GOOGLE_TRANSLATE_API_KEY"):
        return "google"
    if os.environ.get("DEEPL_API_KEY"):
        return "deepl"

    raise RuntimeError(
        "No translation API key found. "
        "Set AZURE_TRANSLATOR_KEY, GEMINI_API_KEY, DEEPSEEK_API_KEY, or DASHSCOPE_API_KEY."
    )


def main(argv: list[str] | None = None) -> int:
    load_dotenv()

    parser = argparse.ArgumentParser(description="Translate EPUB EN→VI")
    parser.add_argument(
        "--version", action="version", version=f"%(prog)s {__version__}"
    )
    parser.add_argument("input")
    parser.add_argument("output", nargs="?")
    parser.add_argument(
        "--engine",
        "-e",
        choices=["auto", "azure", "gemini", "deepseek", "alibaba", "google", "deepl"],
        default="auto",
    )
    parser.add_argument(
        "--items",
        "-i",
        help="Spine item numbers to translate, e.g. 1,3,5 or 2-6 or 1,3-5,8 (see --list)",
    )
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
        default=None,
        help="Model creativity/temperature for Gemini, DeepSeek, and Alibaba",
    )
    parser.add_argument(
        "--glossary",
        "-g",
        type=Path,
        help="Path to glossary TOML file for character pronouns and terms (auto-detects .trans-epub/glossary.toml)",
    )
    parser.add_argument(
        "--fresh",
        action="store_true",
        help="Ignore existing cache, translation fresh",
    )
    args = parser.parse_args(argv)

    out = args.output or args.input.replace(".epub", "_vi.epub")

    only: set[int] | None = None
    if args.items:
        only = set()
        for part in args.items.split(","):
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
        glossary_path=str(args.glossary) if args.glossary else None,
        fresh=args.fresh,
    )
    return 0
