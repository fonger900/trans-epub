import os
import unittest
from unittest.mock import patch

import main


class CliTests(unittest.TestCase):
    def test_auto_engine_prefers_available_provider(self):
        original = {k: os.environ.get(k) for k in ["AZURE_TRANSLATOR_KEY", "GEMINI_API_KEY", "DEEPSEEK_API_KEY"]}
        try:
            os.environ.pop("AZURE_TRANSLATOR_KEY", None)
            os.environ["GEMINI_API_KEY"] = "demo"
            os.environ.pop("DEEPSEEK_API_KEY", None)
            self.assertEqual(main.resolve_engine("auto"), "gemini")
        finally:
            for key, value in original.items():
                if value is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = value

    def test_main_forwards_creativity_option(self):
        with patch.object(main, "translate_epub") as translate_epub:
            main.main(["book.epub", "--engine", "gemini", "--creativity", "0.8"])

        translate_epub.assert_called_once()
        args, kwargs = translate_epub.call_args
        self.assertEqual(args[0], "book.epub")
        self.assertEqual(args[1], "book_vi.epub")
        self.assertEqual(args[2], "gemini")
        self.assertEqual(kwargs["creativity"], 0.8)


if __name__ == "__main__":
    unittest.main()
