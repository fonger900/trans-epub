# Architecture

## Overview

`trans-epub` reads an EPUB, translates each chapter from English to Vietnamese via a configurable AI/cloud engine, and writes a new EPUB. The design is modular with clear separation of concerns across ~1,500 lines of source code.

## Directory Layout

```
trans_epub/
├── __init__.py          # Public API re-exports (31 lines)
├── cli.py               # Argparse entry point, --version
├── config.py            # TOML + env var config (dataclass model)
├── epub_translator.py   # EPUB orchestration: read, thread pool, progress, write
├── html_translator.py   # HTML parse → extract text → batch → translate → reassemble
├── toc.py               # TOC link titles + nav document translation
└── engines/
    ├── __init__.py      # Import all engines to trigger registration
    ├── base.py          # Shared: HTTP session, EngineConfig, LLM_PROMPT, retry, registry
    ├── alibaba.py       # Alibaba DashScope (Qwen) engine
    ├── azure.py         # Azure Cognitive Translator engine
    ├── deepl.py         # DeepL engine
    ├── deepseek.py      # DeepSeek engine
    ├── gemini.py        # Google Gemini engine
    └── google.py        # Google Cloud Translation v2 engine
```

## Translation Pipeline

```
EPUB (.epub)
  │
  ▼
epub_translator.translate_epub()
  │
  ├─ 1. Read EPUB with ebooklib
  ├─ 2. Translate TOC link titles (toc.py)
  ├─ 3. Translate nav document (toc.py → html_translator.translate_html)
  ├─ 4. For each spine item (chapter):
  │      │
  │      ├─ Cache hit? → restore cached content, skip
  │      └─ Cache miss? →
  │            │
  │            ├─ html_translator.translate_html()
  │            │     ├─ Parse HTML with BeautifulSoup (lxml-xml)
  │            │     ├─ Find all translatable nodes (p, h1-h6, li, td, th)
  │            │     ├─ Extract text with emphasis tags intact
  │            │     ├─ Batch by char_limit / elem_limit
  │            │     ├─ For each batch:
  │            │     │     ├─ Call engine.translate(batch)
  │            │     │     ├─ On failure: bisect batch, retry sub-batches
  │            │     │     └─ On wrong count: bisect batch, retry sub-batches
  │            │     └─ Write translations back into HTML nodes
  │            └─ Cache result → write .cache.json
  │
  ├─ 5. Write EPUB with ebooklib
  └─ 6. Repack ZIP to fix CRC-32 mismatches
```

## Module Responsibilities

### `cli.py` (122 lines)

- Loads `.env` via `python-dotenv`
- Uses hardcoded defaults (engine=auto, threads=4, creativity=None)
- Parses `--items` ranges (e.g. `1-5,8`)
- Resolves `auto` engine by checking env vars in a fixed priority order
- `--glossary` / `-g` flag for character pronoun matrix
- `--fresh` flag to ignore cache and translate everything
- Calls `translate_epub()` with parsed args
- Returns exit code 0

### `config.py` (181 lines)

Glossary loading only — no runtime config.

Dataclasses: `CharacterEntry` (pronoun mapping), `Glossary` (characters + terms).

Helpers: `_find_file()` (search .trans-epub/ + ~/.config/...), `_load_toml()` (tomllib with fallback).

- `load_glossary(path=None)` — auto-detect or explicit path
- `build_glossary_prompt(glossary)` — generate LLM prompt section for pronoun consistency

Glossary auto-detection:
1. Explicit `--glossary` path
2. `./.trans-epub/glossary.toml`
3. `~/.config/trans-epub/glossary.toml`

### `epub_translator.py` (276 lines)

- Reads EPUB with `ebooklib.read_epub()`
- Adds `EpubNav` if missing (ebooklib writer bug workaround)
- Maps spine IDs → items via `get_spine_items()`
- **Pre-scan**: counts total/cached/pending chars before translation, displays summary
- **Interactive prompt**: asks y/n before proceeding (skipped when piped/redirected)
- Translatable items processed via `ThreadPoolExecutor` (configurable `--threads`)
- Each thread runs `process_chapter()`:
  - Checks cache (skipped if `--fresh`) → restores or translates
  - Uses per-worker `Rich` progress rows that appear/disappear via a free-list
  - Writes per-chapter cache to `.cache.json` after each chapter
- On completion: writes EPUB, repacks ZIP, cache persists for future runs
- `--fresh` flag ignores cache, translates everything from scratch
- Collects failures and reports them at end with quota troubleshooting tips
- Partial output is still written on failure

#### Threading Model

- Fixed thread pool (`max_workers=threads`)
- Channel-based (free-list) worker slot assignment for progress UI
- `total_chars_lock` protects the running char count (updated from `on_progress` callback)
- `cache_lock` protects cache reads/writes (one chapter at a time writes)
- Worker progress rows use `lock`-protected free-list to claim/release UI slots

#### Caching

- Cache file: `{output}.cache.json` — JSON dict mapping item name → translated HTML
- Written after each chapter completes (crash-safe resume)
- **Persists** across runs — subsequent runs skip already-cached chapters
- `--fresh` flag bypasses cache, translates everything
- `__toc__` key for TOC titles
- Nav document cached under its item name

### `html_translator.py` (167 lines)

Core HTML processing logic:

**Translatable tags** (`TRANSLATE_TAGS`): `p`, `h1`-`h6`, `li`, `td`, `th`

**Preserved blocks**:
- Tags: `table`, `style`, `script` (entire subtree skipped)
- Classes: `note`, `footnote` (entire subtree skipped, including ancestors)

**Text extraction** (`_extract_text_with_emphasis`):
- Emphasis tags (`em`, `strong`, `b`, `i`) are kept as inline markup
- All other child tags are flattened to plain text via `get_text()`

**Batching strategy**:
- Greedy accumulation up to `EngineConfig.char_limit` or `elem_limit`
- No overlap, no sentence splitting — whole elements only

**Retry on failure** (`translate_batch`):
- Recursive bisection: on API failure or count mismatch, split batch in half and retry each half
- Single-element fallback: returns original text unchanged
- Runs after all official retries are exhausted (in-engine retry via `call_with_retry`)

**HTML reassembly**:
- `_clean_translated()` strips all non-emphasis tags from LLM output
- If cleaned text contains `<`, parsed as XML fragment for safe emphasis tag insertion
- Otherwise inserted as plain `NavigableString`

### `toc.py` (74 lines)

- Walks `book.toc` tree recursively to collect all link titles
- Translates titles in bulk via engine
- Caches under `__toc__` key
- Also translates `EpubNav` document by flattening anchor text and passing through `translate_html`

### `engines/base.py` (202 lines)

**`EngineConfig`**: Dataclass holding name, translate callable, char_limit, elem_limit, delay, and optional `RateLimiter`.

**`ENGINES`**: Global `dict[str, EngineConfig]` — populated by each engine module at import time via side-effect registration.

**`http_session`**: Connection-pooled `requests.Session` (pool_maxsize=20).

**`RateLimiter`**: Thread-safe token-bucket limiter — prevents hitting API RPM limits proactively. Default 10 RPM for LLM engines (Gemini: 15 RPM).

**`LLM_PROMPT`**: Shared system prompt for LLM-based engines (Gemini, DeepSeek, Alibaba). Instructs the model to translate EN→VI naturally, preserve emphasis tags, and return JSON. Supports glossary injection via `build_prompt(glossary)`.

**`extract_translations(raw_json)`**: Parses LLM JSON output with repair layers:
1. Strip markdown code fences
2. Standard `json.loads()`
3. Repair unescaped control characters (DeepSeek quirk)
4. `ast.literal_eval()` fallback
5. Accept list, or dict with `translations` key, or first list value found

**`call_with_retry(engine_name, request_fn, parse_fn, max_attempts=7, limiter=None)`**: Generic HTTP retry loop:
- **Proactive**: calls `limiter.wait()` before each request to stay under RPM limits
- Retries on: `RequestException` (network), 429/403 (rate limit / quota), JSONDecodeError, ValueError
- Does **not** retry on: 4xx (except 429/403)
- Exponential backoff: `min(3 * 2^attempt, 60)` seconds
- 429/403 uses `Retry-After` header when available
- Detects quota exceeded keywords in response body (quota, billing, payment required)
- Re-raises on final attempt exhaustion

### Engine Modules (6 files, 48–97 lines each)

Each follows the same pattern:
1. Define a `{name}_translate(texts, creativity=None, glossary=None)` function
2. Read API key from env var
3. Build request payload with glossary-injected prompt (`build_prompt(glossary)` for LLM engines)
4. Wrap in `call_with_retry` with proactive rate limiting
5. Register with `ENGINES[name] = EngineConfig(...)`

All six engines (gemini, deepseek, alibaba, google, deepl, azure) use the shared `call_with_retry` from `base.py` for retry + proactive rate limiting. LLM engines pass `ENGINES[name].limiter` to enforce per-engine RPM limits.

