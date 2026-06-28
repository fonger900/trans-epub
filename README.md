# trans-epub

Dịch EPUB tiếng Anh sang tiếng Việt dùng Azure Translator (free tier: 2M ký tự/tháng).

## Setup

1. Tạo Azure Translator resource (Free F0) tại [Azure Portal](https://portal.azure.com)
2. Copy key và region vào `.env`:

```bash
cp .env.example .env
# Điền AZURE_TRANSLATOR_KEY và AZURE_TRANSLATOR_REGION
```

3. Cài dependencies:

```bash
uv sync
```

## Dùng

### Cách nhanh nhất

```bash
# Tự chọn engine có sẵn trong .env (khuyến nghị)
uv run main.py sach.epub

# Hoặc dùng lệnh chính thức sau khi cài package
uv run trans-epub sach.epub
```

### Các ví dụ hữu ích

```bash
# Chỉ định file output
uv run trans-epub sach.epub output.epub

# Dịch chương cụ thể
uv run trans-epub sach.epub -c 3        # chương 3
uv run trans-epub sach.epub -c 1,3,5    # chương 1, 3, 5
uv run trans-epub sach.epub -c 2-6      # chương 2 đến 6
uv run trans-epub sach.epub -c 1,3-5,8  # kết hợp

# Ép dùng engine cụ thể
uv run trans-epub sach.epub --engine gemini
uv run trans-epub sach.epub --engine azure
```

### Cấu hình nhanh

- Đặt một trong các biến môi trường sau trong .env:
  - AZURE_TRANSLATOR_KEY
  - GEMINI_API_KEY
  - DEEPSEEK_API_KEY
- Nếu không chỉ định `--engine`, chương trình sẽ tự chọn engine đầu tiên có key hợp lệ.

## Resume

Mỗi chương dịch xong được lưu vào `output.epub.cache.json`. Nếu bị ngắt giữa chừng, chạy lại sẽ bỏ qua các chương đã dịch. Cache tự xóa khi dịch xong toàn bộ (khi dùng `-c` thì cache giữ lại để chạy tiếp).
