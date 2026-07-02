# trans-epub

[![Python](https://img.shields.io/badge/python-3.13+-blue.svg)](https://www.python.org/downloads/)
[![License](https://img.shields.io/github/license/fonger900/trans-epub)](LICENSE)

Translate EPUB books from English to Vietnamese using AI translation engines.

**Supported Engines:** Azure Translator, Google Gemini, DeepSeek, Alibaba Qwen  
**Version**: 1.1.0

## 🚀 Features

- Multi-engine AI translation (Azure, Gemini, DeepSeek, Alibaba)
- Fast parallel processing with progress tracking
- Smart caching and resume capability
- Configurable batching and settings
- Workspace deployment support (Alibaba)

## 📋 Prerequisites

- Python 3.13+
- [UV package manager](https://github.com/astral-sh/uv)

## 🛠️ Installation

```bash
# Clone the repository
git clone https://github.com/phongnhhk/trans-epub.git
cd trans-epub

# Install dependencies
uv sync

# Set up API keys
cp .env.example .env
# Edit .env with your API keys
```

## 🔧 Usage

```bash
# Basic translation
uv run trans-epub book.epub

# With specific engine
uv run trans-epub book.epub -e alibaba

# Translate specific chapters
uv run trans-epub book.epub -i 1-5

# Check version
uv run trans-epub --version
```

## ⚙️ Configuration

### Authentication
Copy `.env.example` and add your API keys:

```bash
cp .env.example .env
```

Supported engines:
- `AZURE_TRANSLATOR_KEY` - Azure Translator API key
- `GEMINI_API_KEY` - Google Gemini API key  
- `DEEPSEEK_API_KEY` - DeepSeek API key
- `DASHSCOPE_API_KEY` - Alibaba DashScope API key

### Settings
Create a configuration file at:
- `./.trans-epub/config.toml` (project-specific)
- `~/.config/trans-epub/config.toml` (user-global)

Example config:
```toml
[defaults]
engine = "alibaba"
threads = 4
creativity = 0.3

[engines.alibaba]
model = "qwen-plus"
```

## 💰 Cost Optimization

- **Azure Translator**: $25/Million chars (cheapest for bulk)
- **Alibaba Qwen**: $0.80/Million chars (best value)  
- **DeepSeek**: $2/Million chars (often with free tier)
- **Google Gemini**: $1.50/Million chars (high quality)

## ⏸️ Resume Capability

Each translated chapter is cached in `output.epub.cache.json`. If interrupted, re-run the same command to resume where you left off.

Cache is automatically deleted when translation completes. Use `-i` to keep cache for resumable work.

## 🌐 Alibaba Workspace Support

For custom workspace deployments:
```bash
export DASHSCOPE_WORKSPACE_ID=your-workspace-id
```

## 🤝 Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## 🆘 Support

If you encounter issues, please [open an issue](../../issues) on GitHub.
