# Translation Engines

## Registry Pattern

Engines register themselves via a side-effect import pattern:

```python
# trans_epub/engines/__init__.py  — imports all engine modules
from .gemini import gemini_translate
from .azure import azure_translate
# ...

# Each engine module registers at module level:
ENGINES["gemini"] = EngineConfig(
    name="gemini",
    translate=gemini_translate,
    char_limit=20_000,
    elem_limit=50,
    delay=0,
)
```

The `ENGINES` dict (defined in `base.py`) is the single registry. Adding a new engine requires:
1. Create `trans_epub/engines/{name}.py`
2. Define a translate function
3. Register an `EngineConfig`
4. Import the module in `engines/__init__.py`

## EngineConfig Fields

| Field | Purpose |
|---|---|
| `name` | Engine identifier string |
| `translate` | Callable `(texts: list[str], creativity: float \| None = None, glossary: Glossary \| None = None) -> list[str]` |
| `char_limit` | Max characters per API batch |
| `elem_limit` | Max elements per API batch |
| `delay` | Seconds to sleep between batches (legacy, prefer `limiter`) |
| `limiter` | `RateLimiter` instance — proactive RPM throttling (default: 10 RPM) |

### Choosing Limits

- `char_limit` should be 50-80% of the model's context window (in characters, not tokens) to leave room for the system prompt and response.
- `elem_limit` caps the number of separate paragraphs sent in one request. With greedy batching, `elem_limit` is hit before `char_limit` for very short paragraphs.
- `limiter` controls proactive RPM throttling. Set higher for paid tiers, lower for free tiers. Override: `EngineConfig(..., limiter=RateLimiter(rpm=15))`. Default 10 RPM is safe for most free tiers.

## Engine Types

### LLM-based (Gemini, DeepSeek, Alibaba)

Send a system prompt (`LLM_PROMPT`) plus the texts as a JSON payload. Expect a JSON response with a `translations` array.

```
request:  LLM_PROMPT + json.dumps({"texts": [...texts...]})
response: {"translations": ["...", "...", ...]}
```

All three use `call_with_retry` from `base.py` for automatic retry with exponential backoff and proactive rate limiting.

### HTTP Translation API (Azure, Google Cloud Translation, DeepL)

Send texts as POST body fields. Response structure varies by provider.

- **Azure**: uses own inline retry (8 attempts) + shared `call_with_retry` limiter
- **Google Cloud Translation**: **no retry**
- **DeepL**: **no retry**

## Adding a New Engine

### Quick Start

```python
"""My custom translation engine."""
import os
from .base import ENGINES, EngineConfig, RateLimiter, http_session

def my_translate(texts: list[str], **_kwargs) -> list[str]:
    key = os.environ.get("MY_ENGINE_KEY")
    if not key:
        raise RuntimeError("MY_ENGINE_KEY not found")

    resp = http_session.post(
        "https://api.example.com/translate",
        headers={"Authorization": f"Bearer {key}"},
        json={"text": texts, "source": "en", "target": "vi"},
        timeout=30,
    )
    resp.raise_for_status()
    return [item["translated_text"] for item in resp.json()["translations"]]

ENGINES["my_engine"] = EngineConfig(
    name="my_engine",
    translate=my_translate,
    char_limit=10_000,
    elem_limit=50,
    delay=0,
    limiter=RateLimiter(rpm=30),  # adjust based on API tier
)
```

Then add `from .my_engine import my_translate` to `engines/__init__.py`.

### Adding Retry

For LLM-style engines, wrap the translate function with `call_with_retry` and pass the engine's limiter:

```python
from .base import call_with_retry, extract_translations

def my_translate(texts, creativity=None):
    prompt = LLM_PROMPT + json.dumps({"texts": texts})

    def do_request():
        return http_session.post(url, json={...}, timeout=300)

    def parse(resp):
        return extract_translations(resp.json()["data"])

    return call_with_retry("MyEngine", do_request, parse, limiter=ENGINES["my_engine"].limiter)
```

For HTTP API engines, either:
- Use the shared `call_with_retry` (preferred)
- Or add inline retry (see `azure.py` for pattern)

### Creativity / Temperature

The `creativity` parameter is passed from CLI `--creativity` (default: `config.creativity`). It maps to model temperature:

```python
temperature = DEFAULT_CREATIVITY if creativity is None else creativity
```

Only LLM-based engines use creativity. HTTP API engines ignore it (use `**_kwargs`).

## API Key Resolution

Each engine reads its key from an environment variable:

```python
key = os.environ.get("MY_ENGINE_KEY")
```

API keys come from environment variables only (set in `.env`).

## Testing a New Engine

1. Unit-test the translate function with mocked HTTP
2. Add integration test with `patch.dict(ENGINES, {"my_engine": mock_config})`
3. Test retry with `call_with_retry` (see `tests/test_retries.py`)

See `tests/test_core.py` and `tests/test_html_translator.py` for examples of testing with mocked engines.
