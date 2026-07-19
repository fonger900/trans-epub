"""Core translation logic tests."""

from unittest.mock import MagicMock, patch


from trans_epub.html_translator import translate_html


class TestTranslateHtml:
    """translate_html with shared mock engine fixture."""

    def test_basic_translation(self, mock_engines, simple_html):
        result, char_count = translate_html(simple_html, "test")
        result_str = result.decode("utf-8")
        assert "VI: Hello world" in result_str
        assert char_count > 0

    def test_progress_callback(self, mock_engines, simple_html):
        calls = []

        def cb(batch_num, total_batches, batch_chars):
            calls.append((batch_num, total_batches, batch_chars))

        translate_html(simple_html, "test", progress_cb=cb)
        assert len(calls) > 0
        n, t, c = calls[0]
        assert isinstance(n, int)
        assert isinstance(t, int)
        assert isinstance(c, int)

    def test_empty_input(self, mock_engines):
        result, char_count = translate_html(b"", "test")
        assert result == b""
        assert char_count == 0

    def test_no_translatable_content(self, mock_engines):
        html = b'<html><body><img src="x.jpg" alt=""/></body></html>'
        result, char_count = translate_html(html, "test")
        assert result == html
        assert char_count == 0

    def test_batching_respects_char_limit(self):
        """With a tiny char_limit, texts should be split across batches."""
        cfg = MagicMock()
        cfg.char_limit = 10
        cfg.elem_limit = 50
        cfg.delay = 0
        call_count = 0

        def translate(texts, **_kwargs):
            nonlocal call_count
            call_count += 1
            return [f"T{i}" for i in range(len(texts))]

        cfg.translate = translate

        with patch("trans_epub.html_translator.ENGINES") as eng:
            eng.__getitem__.return_value = cfg
            html = b"<html><body><p>AAAA</p><p>BBBB</p><p>CCCC</p></body></html>"
            result, _ = translate_html(html, "x")

        assert call_count >= 2  # at least 2 batches due to small char_limit

    def test_batching_respects_elem_limit(self):
        """With elem_limit=2, three paragraphs should produce 2 batches."""
        cfg = MagicMock()
        cfg.char_limit = 10_000
        cfg.elem_limit = 2
        cfg.delay = 0
        batch_sizes = []

        def translate(texts, **_kwargs):
            batch_sizes.append(len(texts))
            return [f"T{i}" for i in range(len(texts))]

        cfg.translate = translate

        with patch("trans_epub.html_translator.ENGINES") as eng:
            eng.__getitem__.return_value = cfg
            html = b"<html><body><p>A</p><p>B</p><p>C</p></body></html>"
            translate_html(html, "x")

        assert batch_sizes == [2, 1]

    def test_emphasis_tags_preserved(self, mock_engines, mock_engine_config):
        """Emphasis tags in source should be passed to the engine and preserved."""
        html = b"<p>Hello <em>world</em>!</p>"
        seen_texts = []

        def capture(texts, **_kwargs):
            seen_texts.extend(texts)
            return texts  # return as-is (already contains tags)

        mock_engine_config.translate = capture

        result, _ = translate_html(html, "test")
        result_str = result.decode("utf-8")
        assert "<em>world</em>" in result_str

    def test_literal_angle_bracket_in_translation(
        self, mock_engines, mock_engine_config
    ):
        """Literal '<' in translated text (from LLM) should not break XML parsing.

        Source uses &lt; which BeautifulSoup decodes to '<'. The mock engine
        returns a translation containing '<' — the reassembly must escape it
        so it survives XML encoding as &lt;.
        """
        html = (
            b"<html><body><p>Technical note: x &lt; y is always true</p></body></html>"
        )

        def tricky_translate(texts, **_kwargs):
            return [t.replace("x < y is always true", "x < y luôn đúng") for t in texts]

        mock_engine_config.translate = tricky_translate

        result, _ = translate_html(html, "test")
        result_str = result.decode("utf-8")
        assert "x &lt; y luôn đúng" in result_str

    def test_literal_ampersand_in_translation(self, mock_engines, mock_engine_config):
        """Literal '&' in translated text should survive XML parsing as &amp;."""
        html = b"<html><body><p>Rock &amp; roll music</p></body></html>"

        def tricky_translate(texts, **_kwargs):
            return [t.replace("Rock & roll", "Rock & nhạc") for t in texts]

        mock_engine_config.translate = tricky_translate

        result, _ = translate_html(html, "test")
        result_str = result.decode("utf-8")
        assert "Rock &amp; nhạc" in result_str


class TestTranslateHtmlFallback:
    """translate_html fallback behaviour when the API returns wrong counts."""

    def test_mismatched_count_bisects(self, mock_engines, mock_engine_config):
        """When engine returns wrong count, fallback should bisect and retry."""
        html = b"<html><body><p>A</p><p>B</p></body></html>"
        call_log = []

        def flaky(texts, **_kwargs):
            call_log.append(len(texts))
            if len(texts) == 2:
                return ["only_one"]  # wrong count
            return [f"VI: {t}" for t in texts]

        mock_engine_config.translate = flaky

        result, _ = translate_html(html, "test")
        assert call_log == [2, 2, 1, 1]  # first 2 fails → retry @2 → two singles
        assert b"VI: A" in result
        assert b"VI: B" in result

    def test_single_element_fallback_returns_original(
        self, mock_engines, mock_engine_config
    ):
        """When a single-element batch fails, return original text."""
        html = b"<p>Keep me</p>"

        def fail(_texts, **_kwargs):
            raise RuntimeError("API error")

        mock_engine_config.translate = fail

        result, _ = translate_html(html, "test")
        assert b"Keep me" in result
