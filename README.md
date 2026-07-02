# trans-epub

Dịch EPUB tiếng Anh sang tiếng Việt. Hỗ trợ ba engine: Azure Translator, Google Gemini, DeepSeek.

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

## Resume

Mỗi item dịch xong được lưu vào `output.epub.cache.json`. Nếu bị ngắt giữa chừng, chạy lại lệnh cũ sẽ bỏ qua các item đã dịch. Cache tự xóa khi dịch xong toàn bộ; khi dùng `-i` thì cache giữ lại để có thể chạy tiếp.
