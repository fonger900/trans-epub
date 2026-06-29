import unittest

from ebooklib import epub

import main


class TranslateTocTests(unittest.TestCase):
    def test_translate_toc_and_nav_updates_titles_and_nav_links(self):
        def fake_translate(texts):
            return [f"TR:{text}" for text in texts]

        original_engines = main.ENGINES
        main.ENGINES = {"test": (fake_translate, 10_000, 100, 0)}
        try:
            book = epub.EpubBook()
            nav = epub.EpubNav()
            nav.set_content(b"<nav><ol><li><a href=\"chapter.xhtml\">Introduction</a></li></ol></nav>")
            book.add_item(nav)
            book.toc = [epub.Link("chapter.xhtml", "Introduction", "intro")]

            main.translate_toc_and_nav(book, "test")

            self.assertEqual(book.toc[0].title, "TR:Introduction")
            nav_html = nav.get_content().decode("utf-8")
            self.assertIn('href="chapter.xhtml"', nav_html)
            self.assertIn("TR:Introduction", nav_html)
        finally:
            main.ENGINES = original_engines


if __name__ == "__main__":
    unittest.main()
