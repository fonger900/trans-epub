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

### Cách dùng đơn giản nhất

```bash
cd /home/phong/Projects/trans-epub
source .venv/bin/activate
python main.py sach.epub
```

### Các ví dụ hữu ích

```bash
# Chỉ định file output
python main.py sach.epub output.epub

# Dịch item cụ thể (xem số thứ tự bằng --list)
python main.py sach.epub -i 3        # item 3
python main.py sach.epub -i 1,3,5    # item 1, 3, 5
python main.py sach.epub -i 2-6      # item 2 đến 6
python main.py sach.epub -i 1,3-5,8  # kết hợp

# Ép dùng engine cụ thể
python main.py sach.epub --engine gemini
python main.py sach.epub --engine azure

# Chỉnh mức sáng tạo của model
python main.py sach.epub --engine gemini --creativity 0.8
python main.py sach.epub --engine deepseek --creativity 0.2
```

### Cấu hình nhanh

- Tạo file `.env` trong thư mục dự án.
- Chỉ cần đặt một trong các biến môi trường sau:
  - `AZURE_TRANSLATOR_KEY`
  - `GEMINI_API_KEY`
  - `DEEPSEEK_API_KEY`
- Nếu không chỉ định `--engine`, chương trình sẽ tự chọn engine đầu tiên có key hợp lệ.
- `--creativity` điều chỉnh `temperature` cho Gemini và DeepSeek; bỏ qua để dùng mặc định của từng engine.

## Resume

Mỗi chương dịch xong được lưu vào `output.epub.cache.json`. Nếu bị ngắt giữa chừng, chạy lại sẽ bỏ qua các chương đã dịch. Cache tự xóa khi dịch xong toàn bộ (khi dùng `-c` thì cache giữ lại để chạy tiếp).
