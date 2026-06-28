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

```bash
# Dịch toàn bộ → tạo ra sach_vi.epub
uv run main.py sach.epub

# Chỉ định file output
uv run main.py sach.epub output.epub

# Dịch chương cụ thể
uv run main.py sach.epub -c 3        # chương 3
uv run main.py sach.epub -c 1,3,5    # chương 1, 3, 5
uv run main.py sach.epub -c 2-6      # chương 2 đến 6
uv run main.py sach.epub -c 1,3-5,8  # kết hợp
```

## Resume

Mỗi chương dịch xong được lưu vào `output.epub.cache.json`. Nếu bị ngắt giữa chừng, chạy lại sẽ bỏ qua các chương đã dịch. Cache tự xóa khi dịch xong toàn bộ (khi dùng `-c` thì cache giữ lại để chạy tiếp).
