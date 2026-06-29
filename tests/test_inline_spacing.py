import unittest

import main


class InlineSpacingTests(unittest.TestCase):
    def test_translate_html_preserves_spaces_around_inline_tags(self):
        def fake_translate(texts):
            return [t.replace("hành", "hành ").replace("bởi", " bởi") for t in texts]

        original = {"test": (fake_translate, 10_000, 100, 0)}
        original_engines = main.ENGINES
        main.ENGINES = original
        try:
            html = "<p>hành<b>an toàn</b>bởi</p>".encode("utf-8")
            translated, _ = main.translate_html(html, "test")
        finally:
            main.ENGINES = original_engines

        result = translated.decode("utf-8")
        self.assertIn('hành ', result)
        self.assertIn('<b>an toàn</b>', result)
        self.assertIn(' bởi', result)


if __name__ == "__main__":
    unittest.main()
