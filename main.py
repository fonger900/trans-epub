"""
EPUB EN→VI translator — supports Azure Translator and Google Gemini.
Usage: python main.py input.epub [output.epub] [--engine azure|gemini|deepseek] [--creativity N]
"""
import os, json, argparse, time, requests, threading, re
from pathlib import Path
from dotenv import load_dotenv
from ebooklib import epub, ITEM_DOCUMENT
from bs4 import BeautifulSoup
from concurrent.futures import ThreadPoolExecutor

load_dotenv()

# Initialize thread-safe global session for requests connection pooling (Keep-Alive)
http_session = requests.Session()
adapter = requests.adapters.HTTPAdapter(pool_connections=20, pool_maxsize=20)
http_session.mount("https://", adapter)
http_session.mount("http://", adapter)

TRANSLATE_TAGS = {"p", "h1", "h2", "h3", "h4", "h5", "h6", "li", "td", "th"}
BLOCK_TAGS = TRANSLATE_TAGS  # tags that should not be nested inside each other
PRESERVE_TAGS = {"table", "style", "script"}
PRESERVE_CLASSES = {"note", "footnote"}
DEFAULT_DEEPSEEK_CREATIVITY = 0.4

# ── Azure ──────────────────────────────────────────────────────────────────────

def azure_translate(texts: list[str]) -> list[str]:
    import uuid
    key = os.environ["AZURE_TRANSLATOR_KEY"]
    region = os.environ.get("AZURE_TRANSLATOR_REGION", "global")
    for attempt in range(8):
        resp = http_session.post(
            "https://api.cognitive.microsofttranslator.com/translate",
            params={"api-version": "3.0", "from": "en", "to": "vi"},
            headers={
                "Ocp-Apim-Subscription-Key": key,
                "Ocp-Apim-Subscription-Region": region,
                "Content-type": "application/json",
                "X-ClientTraceId": str(uuid.uuid4()),
            },
            json=[{"text": t} for t in texts],
            timeout=30,
        )
        if resp.status_code == 429:
            wait = int(resp.headers.get("Retry-After", 2 ** attempt))
            print(f"\n    Rate limited, waiting {wait}s...", end=" ", flush=True)
            time.sleep(wait)
            continue
        resp.raise_for_status()
        return [r["translations"][0]["text"] for r in resp.json()]
    resp.raise_for_status()


def extract_translations(raw_json: str) -> list[str]:
    raw_json = raw_json.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
    data = json.loads(raw_json)
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        if "translations" in data:
            return data["translations"]
        for v in data.values():
            if isinstance(v, list):
                return v
    raise ValueError("Invalid JSON translation response format")


# ── Gemini ─────────────────────────────────────────────────────────────────────

def gemini_translate(texts: list[str], creativity: float | None = None) -> list[str]:
    key = os.environ["GEMINI_API_KEY"]
    generation_config = {"responseMimeType": "application/json"}
    if creativity is not None:
        generation_config["temperature"] = creativity
    prompt = (
        "You are a professional literary translator. Translate the following consecutive paragraphs of a book from English to Vietnamese.\n"
        "Guidelines:\n"
        "- The translation must sound natural, idiomatic, and fluent in Vietnamese (thuần Việt, thoát ý).\n"
        "- Do not translate literally (word-for-word). Adapt English idioms, passive voice, and complex structures to natural Vietnamese phrasing.\n"
        "- Maintain the tone, style, and flow of the original text across the paragraphs (they are in consecutive order).\n"
        "- Return a JSON object with a single key 'translations' containing the array of translated strings in the exact same order.\n\n"
        + json.dumps({"texts": texts}, ensure_ascii=False)
    )
    for attempt in range(5):
        resp = http_session.post(
            f"https://generativelanguage.googleapis.com/v1beta/models/gemini-3.5-flash:generateContent?key={key}",
            json={
                "contents": [{"parts": [{"text": prompt}]}],
                "generationConfig": generation_config,
            },
            timeout=120,
        )
        if resp.status_code == 429:
            wait = 2 ** attempt
            print(f"\n    429: {resp.json().get('error', {}).get('message', resp.text)}")
            print(f"    Waiting {wait}s...", end=" ", flush=True)
            time.sleep(wait)
            continue
        resp.raise_for_status()
        raw = resp.json()["candidates"][0]["content"]["parts"][0]["text"]
        return extract_translations(raw)
    resp.raise_for_status()


# ── DeepSeek ──────────────────────────────────────────────────────────────────

def deepseek_translate(texts: list[str], creativity: float | None = None) -> list[str]:
    key = os.environ["DEEPSEEK_API_KEY"]
    temperature = DEFAULT_DEEPSEEK_CREATIVITY if creativity is None else creativity
    prompt = (
        "You are a professional literary translator. Translate the following consecutive paragraphs of a book from English to Vietnamese.\n"
        "Guidelines:\n"
        "- The translation must sound natural, idiomatic, and fluent in Vietnamese (thuần Việt, thoát ý).\n"
        "- Do not translate literally (word-for-word). Adapt English idioms, passive voice, and complex structures to natural Vietnamese phrasing.\n"
        "- Maintain the tone, style, and flow of the original text across the paragraphs (they are in consecutive order).\n"
        "- Return a JSON object with a single key 'translations' containing the array of translated strings in the exact same order.\n\n"
        + json.dumps({"texts": texts}, ensure_ascii=False)
    )
    for attempt in range(5):
        resp = http_session.post(
            "https://api.deepseek.com/chat/completions",
            headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
            json={
                "model": "deepseek-chat",
                "messages": [{"role": "user", "content": prompt}],
                "temperature": temperature,
                "max_tokens": 8192,
                "response_format": {"type": "json_object"}
            },
            timeout=120,
        )
        if resp.status_code == 429:
            wait = 2 ** attempt
            print(f"\n    Rate limited, waiting {wait}s...", end=" ", flush=True)
            time.sleep(wait)
            continue
        resp.raise_for_status()
        raw = resp.json()["choices"][0]["message"]["content"]
        return extract_translations(raw)
    resp.raise_for_status()


# ── Core ───────────────────────────────────────────────────────────────────────

ENGINES = {"azure":    (azure_translate,    40_000, 100, 1.5),
           "gemini":   (gemini_translate,   20_000,  50, 0),
           "deepseek": (deepseek_translate, 10_000,  25, 0)}
#                                       char_limit  elem_limit  delay


def resolve_engine(engine: str) -> str:
    if engine != "auto":
        return engine
    if os.environ.get("AZURE_TRANSLATOR_KEY"):
        return "azure"
    if os.environ.get("GEMINI_API_KEY"):
        return "gemini"
    if os.environ.get("DEEPSEEK_API_KEY"):
        return "deepseek"
    raise RuntimeError("No translation API key found. Set AZURE_TRANSLATOR_KEY, GEMINI_API_KEY, or DEEPSEEK_API_KEY.")


def translate_texts(engine: str, texts: list[str], creativity: float | None = None) -> list[str]:
    translate_fn, _, _, _ = ENGINES[engine]
    if engine == "gemini":
        return translate_fn(texts, creativity=creativity)
    if engine == "deepseek":
        return translate_fn(texts, creativity=creativity)
    return translate_fn(texts)


def translate_html(html_bytes: bytes, engine: str, creativity: float | None = None) -> tuple[bytes, int]:
    _, char_limit, elem_limit, delay = ENGINES[engine]
    soup = BeautifulSoup(html_bytes, "lxml-xml")

    def should_preserve(tag) -> bool:
        for current in [tag, *tag.parents]:
            if getattr(current, "name", None) in PRESERVE_TAGS:
                return True
            classes = current.get("class", []) if hasattr(current, "get") else []
            if isinstance(classes, str):
                classes = classes.split()
            if any(cls in PRESERVE_CLASSES for cls in classes):
                return True
        return False

    nodes = [
        tag for tag in soup.find_all(TRANSLATE_TAGS)
        if tag.get_text(strip=True) and not tag.find(BLOCK_TAGS) and not should_preserve(tag)
    ]
    if not nodes:
        return html_bytes, 0

    text_nodes: list[tuple] = []
    texts: list[str] = []

    for node in nodes:
        for child in node.find_all(string=True):
            text = str(child)
            if not text.strip():
                continue

            match = re.match(r"^(\s*)(.*?)(\s*)$", text, flags=re.S)
            if match:
                prefix, core, suffix = match.groups()
            else:
                prefix, core, suffix = "", text, ""

            text_nodes.append((child, prefix, core, suffix))
            texts.append(core)

    if not texts:
        return html_bytes, 0

    char_count = sum(len(text) for text in texts)
    translated_all: list[str] = []
    batch, batch_len = [], 0

    def collapse_translation(parts: list[str]) -> str:
        return " ".join(part.strip() for part in parts if part.strip())

    def translate_batch(batch_texts: list[str]) -> list[str]:
        translated_batch = translate_texts(engine, batch_texts, creativity=creativity)
        if len(translated_batch) == len(batch_texts):
            return translated_batch
        if len(batch_texts) == 1:
            return [collapse_translation(translated_batch)]

        midpoint = len(batch_texts) // 2
        return translate_batch(batch_texts[:midpoint]) + translate_batch(batch_texts[midpoint:])

    for text in texts:
        if (batch_len + len(text) > char_limit or len(batch) >= elem_limit) and batch:
            if delay:
                time.sleep(delay)
            translated_all.extend(translate_batch(batch))
            batch, batch_len = [], 0
        batch.append(text)
        batch_len += len(text)
    if batch:
        if delay:
            time.sleep(delay)
        translated_all.extend(translate_batch(batch))

    for (child, prefix, core, suffix), translated in zip(text_nodes, translated_all):
        child.replace_with(f"{prefix}{translated}{suffix}")

    return soup.encode("utf-8"), char_count


def translate_toc_and_nav(book: epub.EpubBook, engine: str, creativity: float | None = None) -> None:
    titles = []
    links = []

    def walk_links(link_list):
        for link in link_list:
            if getattr(link, "title", None):
                titles.append(link.title)
                links.append(link)
            if getattr(link, "content", None):
                walk_links(link.content)

    walk_links(book.toc or [])

    if titles:
        translated_titles = translate_texts(engine, titles, creativity=creativity)
        for link, translated in zip(links, translated_titles):
            link.title = translated

    for item in book.get_items():
        if not isinstance(item, epub.EpubNav):
            continue
        content = item.get_content().decode("utf-8")
        soup = BeautifulSoup(content, "html.parser")
        for anchor in soup.find_all("a"):
            text = anchor.get_text(strip=True)
            if text:
                anchor.string = text
        translated_html, _ = translate_html(soup.encode("utf-8"), engine, creativity=creativity)
        item.set_content(translated_html)
        break


def get_spine_items(book: epub.EpubBook) -> list:
    spine_ids = [idref for idref, _ in book.spine]
    by_id = {item.get_id(): item for item in book.get_items_of_type(ITEM_DOCUMENT)}
    return [by_id[sid] for sid in spine_ids if sid in by_id]


def translate_epub(input_path: str, output_path: str, engine: str,
                   only_chapters: set[int] | None = None, list_only: bool = False,
                   threads: int = 4, creativity: float | None = None) -> None:
    cache_path = Path(output_path + ".cache.json")
    cache: dict[str, str] = json.loads(cache_path.read_text()) if cache_path.exists() else {}

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

    def process_chapter(i, item):
        nonlocal total_chars
        name = item.get_name()
        
        if only_chapters and i not in only_chapters:
            with cache_lock:
                cached_content = cache.get(name)
            if cached_content:
                item.set_content(cached_content.encode("utf-8"))
            return

        with cache_lock:
            in_cache = name in cache
            if in_cache:
                cached_content = cache[name]

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
            raise e

        with total_chars_lock:
            total_chars += chars

        with cache_lock:
            cache[name] = translated.decode("utf-8")
            cache_path.write_text(json.dumps(cache, ensure_ascii=False))

        item.set_content(translated)
        safe_print(f"  [{i}/{total}] Done: {name} ({chars:,} chars)")

    # Execute chapter translations in parallel if using multiple threads
    if threads > 1:
        with ThreadPoolExecutor(max_workers=threads) as executor:
            futures = [executor.submit(process_chapter, i, item) for i, item in enumerate(items, 1)]
            for future in futures:
                future.result()
    else:
        for i, item in enumerate(items, 1):
            process_chapter(i, item)

    epub.write_epub(output_path, book)
    if not only_chapters:
        cache_path.unlink(missing_ok=True)
    print(f"\nDone → {output_path}  (translated ~{total_chars:,} chars)")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Translate EPUB EN→VI")
    parser.add_argument("input")
    parser.add_argument("output", nargs="?")
    parser.add_argument("--engine", "-e", choices=["auto", "azure", "gemini", "deepseek"], default="auto")
    parser.add_argument("--chapters", "-c", help="e.g. 1,3,5 or 2-6 or 1,3-5,8")
    parser.add_argument("--list", "-l", action="store_true")
    parser.add_argument("--threads", "-t", type=int, default=4, help="Number of parallel translation threads")
    parser.add_argument("--creativity", type=float, help="Model creativity/temperature for Gemini and DeepSeek")
    args = parser.parse_args(argv)

    out = args.output or args.input.replace(".epub", "_vi.epub")
    only = None
    if args.chapters:
        only = set()
        for part in args.chapters.split(","):
            if "-" in part:
                a, b = part.split("-", 1)
                only.update(range(int(a), int(b) + 1))
            else:
                only.add(int(part))

    engine = resolve_engine(args.engine)
    translate_epub(args.input, out, engine, only, list_only=args.list, threads=args.threads, creativity=args.creativity)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
