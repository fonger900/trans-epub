# trans-epub

Dịch EPUB tiếng Anh sang tiếng Việt. Hỗ trợ nhiều engine: Azure Translator, Google Gemini, DeepSeek, Alibaba Qwen.

**Version**: 1.1.0

## Setup

1. Cài dependencies:

```bash
uv sync
```

2. Tạo file `.env` và điền API key của engine muốn dùng:

```bash
cp .env.example .env
```

| Biến | Engine |
|---|---|
| `AZURE_TRANSLATOR_KEY`, `AZURE_TRANSLATOR_REGION` | Azure Translator (free tier: 2M ký tự/tháng) |
| `GEMINI_API_KEY` | Google Gemini |
| `DASHSCOPE_API_KEY` | Alibaba Cloud Model Studio |
| `DASHSCOPE_API_BASE` | (optional) Alibaba workspace endpoint, defaults to `dashscope.aliyuncs.com/compatible-mode/v1` |
| `DASHSCOPE_MODEL` | (optional) Model name, defaults to `qwen3-flash` |

Chỉ cần set key của một engine là đủ.

## Dùng

```bash
# Dịch toàn bộ (tự chọn engine từ key có sẵn)
trans-epub sach.epub

# Chỉ định file output
trans-epub sach.epub output.epub

# Xem danh sách spine items (để biết số thứ tự dùng với -i)
trans-epub sach.epub --list

# Dịch item cụ thể
trans-epub sach.epub -i 3        # item 3
trans-epub sach.epub -i 1,3,5    # item 1, 3, 5
trans-epub sach.epub -i 2-6      # item 2 đến 6
trans-epub sach.epub -i 1,3-5,8  # kết hợp

# Chọn engine
trans-epub sach.epub -e gemini
trans-epub sach.epub -e azure
trans-epub sach.epub -e deepseek
trans-epub sach.epub -e alibaba

# Số thread song song (mặc định: 4)
trans-epub sach.epub -t 8

# Chỉnh độ sáng tạo của model (Gemini, DeepSeek, và Alibaba)
trans-epub sach.epub -e gemini --creativity 0.8
trans-epub sach.epub -e deepseek --creativity 0.2
trans-epub sach.epub -e alibaba --creativity 0.5
```

## Version

Check the current version:

```bash
trans-epub --version
```

## Resume

Mỗi item dịch xong được lưu vào `output.epub.cache.json`. Nếu bị ngắt giữa chừng, chạy lại lệnh cũ sẽ bỏ qua các item đã dịch. Cache tự xóa khi dịch xong toàn bộ; khi dùng `-i` thì cache giữ lại để có thể chạy tiếp.

## Configuration

Trans-epub supports configuration via TOML files for managing API keys, defaults, and preferences.

### Setup

Create a configuration file at one of these locations:

- `./.trans-epub/config.toml` (project-specific)
- `~/.config/trans-epub/config.toml` (user-global)

Use the provided example as a starting point:

```bash
cp .trans-epub/config.example.toml ~/.config/trans-epub/config.toml
```

### Configuration Options

#### Default Settings

- `engine`: Default translation engine (azure, alibaba, gemini, deepseek)
- `threads`: Number of concurrent translation threads
- `creativity`: Default creativity for LLM engines (0.0-1.0)
- `timeout`: Timeout for API calls in seconds

#### Engine-Specific Keys

Each engine section supports:

- `api_key`: API key (can also be set via environment variables)
- `base_url`: API endpoint URL
- `model`: Model name to use
- `creativity`: Default creativity for this engine
- `char_limit`, `elem_limit`: Batching limits

#### Batching

Controls how text is chunked for API calls:

- `char_limit`: Max characters per batch
- `elem_limit`: Max HTML elements per batch
- `delay`: Delay between API calls (for rate limiting)

#### Caching

- `enabled`: Whether caching is enabled
- `ttl_days`: Days before cache expires (0 = never expire)
- `location`: Where to store cache files

### Environment Variable Precedence

Environment variables override configuration file settings:

- `TRANS_EPUB_ENGINE`: Default engine
- `TRANS_EPUB_THREADS`: Thread count
- `TRANS_EPUB_CREATIVITY`: Creativity value
- `AZURE_TRANSLATOR_KEY`, `GEMINI_API_KEY`, `DEEPSEEK_API_KEY`, `DASHSCOPE_API_KEY`: API keys
