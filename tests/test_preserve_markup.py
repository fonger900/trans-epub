import unittest

import main


class PreserveMarkupTests(unittest.TestCase):
    def test_translate_html_preserves_links_and_font_tags(self):
        def fake_translate(texts):
            return [f"TR:{text}" for text in texts]

        original = {"test": (fake_translate, 10_000, 100, 0)}
        original_engines = main.ENGINES
        main.ENGINES = original
        try:
            html_bytes, char_count = main.translate_html(
                b"<p>Hello <a href=\"https://example.com\">world</a> <span style=\"font-size: 12px;\">again</span>!</p>",
                "test",
            )
        finally:
            main.ENGINES = original_engines

        result = html_bytes.decode("utf-8")
        self.assertIn('<a href="https://example.com">TR:world</a>', result)
        self.assertIn('<span style="font-size: 12px;">TR:again</span>', result)
        self.assertIn('TR:Hello', result)
        self.assertIn('TR:!', result)
        self.assertGreater(char_count, 0)


if __name__ == "__main__":
    unittest.main()
