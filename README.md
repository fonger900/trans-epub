# trans-epub

Convert EPUB books from English to Vietnamese using AI translation engines.

**Supported Engines:** Azure Translator, Google Gemini, DeepSeek, Alibaba Qwen  
**Version**: 1.1.0

## Installation

1. Install dependencies:
```bash
uv sync
```

## Authentication

1. Copy and edit the environment file:
```bash
cp .env.example .env
```

2. Fill in your API key for at least one engine:

| Variable | Engine | Notes |
|----------|--------|-------|
| `AZURE_TRANSLATOR_KEY` | Azure Translator | Free tier: 2M chars/month |
| `AZURE_TRANSLATOR_REGION` | Azure Translator | Optional, default: `global` |
| `GEMINI_API_KEY` | Google Gemini | |
| `DEEPSEEK_API_KEY` | DeepSeek | |
| `DASHSCOPE_API_KEY` | Alibaba DashScope | Required for Alibaba |
| `DASHSCOPE_API_BASE` | Alibaba DashScope | Optional, custom endpoint |
| `DASHSCOPE_WORKSPACE_ID` | Alibaba DashScope | Optional, for workspace deployments |

**Important:** Only API keys go in `.env` (secrets). Configuration options like threads, creativity, and models go in the config file (see below).

## Basic Usage

```bash
# Translate entire book (auto-detect engine from available key)
trans-epub book.epub

# Specify output file
trans-epub book.epub translated_book.epub

# Select specific engine
trans-epub book.epub -e azure
trans-epub book.epub -e alibaba
trans-epub book.epub -e gemini
trans-epub book.epub -e deepseek

# Parallel processing (default: 4 threads)
trans-epub book.epub -t 8

# Adjust model creativity (for LLM engines: Gemini, DeepSeek, Alibaba)
trans-epub book.epub -e alibaba --creativity 0.5
```

## Advanced Usage

### Chapter Selection
```bash
# List all chapters with numbers
trans-epub book.epub --list

# Translate specific chapters
trans-epub book.epub -i 3        # Chapter 3 only
trans-epub book.epub -i 1,3,5    # Chapters 1, 3, and 5
trans-epub book.epub -i 2-6      # Chapters 2 through 6
trans-epub book.epub -i 1,3-5,8  # Mixed selection
```

### Resume Interrupted Translations
Each translated chapter is cached in `output.epub.cache.json`. If interrupted, re-run the same command to resume where you left off.

Cache is automatically deleted when translation completes. Use `-i` to keep cache for resumable work.

## Configuration

### Setup
Create a configuration file at one of these locations:
- `./.trans-epub/config.toml` (project-specific)
- `~/.config/trans-epub/config.toml` (user-global)

Use the example file as a starting point:
```bash
cp .trans-epub/config.example.toml ~/.config/trans-epub/config.toml
```

### Common Configuration Options

**Default Settings:**
```toml
[defaults]
engine = "azure"        # Default engine (azure/alibaba/gemini/deepseek)
threads = 4            # Parallel translation threads
creativity = 0.3       # Default creativity (0.0-1.0) for LLM engines
timeout = 300          # API call timeout in seconds
```

**Engine-Specific Settings:**
```toml
[engines.alibaba]
model = "qwen-plus"    # Model variant
creativity = 0.4       # Default creativity for this engine
char_limit = 8000      # Max chars per API request

[engines.gemini]
model = "gemini-3.5-flash"
creativity = 0.3

[batching]
char_limit = 10000     # Default max characters per batch
elem_limit = 25        # Default max elements per batch
delay = 0.0            # Delay between API calls (rate limiting)

[caching]
enabled = true         # Enable translation caching
ttl_days = 30          # Cache expiration (0 = never expire)
location = "./cache"   # Cache directory
```

### Alibaba Engine Specifics

The Alibaba engine supports multiple model variants:
- `qwen-max`: Large context, high quality, higher cost
- `qwen-plus`: Balanced performance 
- `qwen-turbo`: Fast, economical
- `qwen-mt-plus`: Optimized for machine translation

For workspace deployments:
```bash
export DASHSCOPE_WORKSPACE_ID=your-workspace-id
```

## Environment Variable Override

You can override config file settings with environment variables:

- `TRANS_EPUB_ENGINE` - Default engine
- `TRANS_EPUB_THREADS` - Thread count  
- `TRANS_EPUB_CREATIVITY` - Creativity value
- `TRANS_EPUB_TIMEOUT` - Timeout in seconds

## Version Information

Check the current version:
```bash
trans-epub --version
```

## Cost Optimization Tips

- **Azure Translator** (~$25/Million chars): Cheapest for high volume
- **Alibaba Qwen** (~$0.80/Million chars): Good quality-to-cost ratio  
- **DeepSeek** (~$2/Million chars): Often has free tier
- **Gemini** (~$1.50/Million chars): High quality

Use caching and selective chapter translation to minimize costs during testing.