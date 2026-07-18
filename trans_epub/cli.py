"""Command-line interface for trans-epub."""

import argparse
import os
from pathlib import Path

from dotenv import load_dotenv

from .config import _find_file
from .epub_translator import translate_epub

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("trans-epub")
except PackageNotFoundError:
    __version__ = "unknown"

_ENV_KEYS = [
    ("AZURE_TRANSLATOR_KEY", "azure"),
    ("GEMINI_API_KEY", "gemini"),
    ("DEEPSEEK_API_KEY", "deepseek"),
    ("DASHSCOPE_API_KEY", "alibaba"),
    ("GOOGLE_TRANSLATE_API_KEY", "google"),
    ("DEEPL_API_KEY", "deepl"),
]


def resolve_engine(engine: str) -> str:
    """Resolve 'auto' to the first engine whose API key is present."""
    if engine != "auto":
        return engine

    for env_key, name in _ENV_KEYS:
        if os.environ.get(env_key):
            return name

    all_keys = ", ".join(k for k, _ in _ENV_KEYS)
    raise RuntimeError(f"No translation API key found. Set one of: {all_keys}.")


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
    parser.add_argument("--list", "-l", action="store_true", help="List spine items with character counts")
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
    parser.add_argument(
        "--dry-run",
        "-n",
        action="store_true",
        help="Validate glossary, count chars, estimate cost without translating",
    )
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Show detailed per-request logging and retry information",
    )
    parser.add_argument(
        "--prompt",
        "-p",
        type=Path,
        help="Path to a text file with additional prompt instructions for this book (auto-detects .trans-epub/prompt.txt)",
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

    # Resolve extra prompt: explicit --prompt flag or auto-detect
    extra_prompt = ""
    prompt_file: Path | None = args.prompt
    if not prompt_file:
        prompt_file = _find_file("prompt.txt")
    if prompt_file and prompt_file.exists():
        extra_prompt = prompt_file.read_text(encoding="utf-8").strip()

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
        dry_run=args.dry_run,
        verbose=args.verbose,
        extra_prompt=extra_prompt,
    )
    return 0
