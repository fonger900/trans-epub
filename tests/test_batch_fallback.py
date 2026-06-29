import unittest

import main


class BatchFallbackTests(unittest.TestCase):
    def test_translate_html_fallback_recovers_by_splitting_batch(self):
        translations = {"X1": "one", "X2": "two", "X3": "three"}

        def fake_translate(texts):
            if len(texts) == 3:
                return ["one", "two"]
            return [translations[text] for text in texts]

        original = {"test": (fake_translate, 1000, 100, 0)}
        original_engines = main.ENGINES
        main.ENGINES = original
        try:
            html = "<p>X1 <b>X2</b> X3</p>".encode("utf-8")
            translated, _ = main.translate_html(html, "test")
        finally:
            main.ENGINES = original_engines

        self.assertIn("one", translated.decode("utf-8"))
        self.assertIn("two", translated.decode("utf-8"))
        self.assertIn("three", translated.decode("utf-8"))

    def test_translate_html_fallback_collapses_split_single_response(self):
        translations = {"X1": "one", "X2": "two"}

        def fake_translate(texts):
            if len(texts) == 2:
                return ["one"]
            if texts == ["X2"]:
                return ["three", "four"]
            return [translations[texts[0]]]

        original = {"test": (fake_translate, 1000, 100, 0)}
        original_engines = main.ENGINES
        main.ENGINES = original
        try:
            html = "<p>X1 <b>X2</b></p>".encode("utf-8")
            translated, _ = main.translate_html(html, "test")
        finally:
            main.ENGINES = original_engines

        result = translated.decode("utf-8")
        self.assertIn("one", result)
        self.assertIn("three four", result)


if __name__ == "__main__":
    unittest.main()
