"""Tests for glossary loading."""

import tempfile
from pathlib import Path

from trans_epub.config import (
    CharacterEntry,
    Glossary,
    _find_file,
    _load_toml,
    build_glossary_prompt,
    load_glossary,
)


class TestFindFile:
    def test_returns_path_when_exists(self, tmp_path, monkeypatch):
        (tmp_path / "glossary.toml").write_text("")
        monkeypatch.setattr("trans_epub.config._CONFIG_DIR", tmp_path)
        result = _find_file("glossary.toml")
        assert result is not None
        assert result.name == "glossary.toml"

    def test_returns_none_when_not_found(self, monkeypatch):
        monkeypatch.setattr(
            "trans_epub.config._CONFIG_DIR", Path("/nonexistent_dir_xyz")
        )
        monkeypatch.setattr(
            "trans_epub.config._USER_CONFIG_DIR", Path("/nonexistent_dir_xyz")
        )
        assert _find_file("glossary.toml") is None


class TestLoadToml:
    def test_loads_valid_toml(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".toml", delete=False) as f:
            f.write('[characters]\nJohn = "anh"\n')
            f.flush()
            data = _load_toml(Path(f.name))
            assert data["characters"]["John"] == "anh"
            Path(f.name).unlink()

    def test_returns_empty_on_invalid(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".toml", delete=False) as f:
            f.write("not valid toml[[[")
            f.flush()
            data = _load_toml(Path(f.name))
            assert data == {}
            Path(f.name).unlink()


class TestLoadGlossary:
    def test_simple_character(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".toml", delete=False) as f:
            f.write('[characters]\nJohn = "anh"\n')
            f.flush()
            glossary = load_glossary(Path(f.name))
            assert glossary is not None
            assert "John" in glossary.characters
            assert glossary.characters["John"].address == "anh"
            Path(f.name).unlink()

    def test_detailed_character(self):
        toml = """\
[characters.John]
self = "tôi"
form = "anh"
narrator = "anh ấy"
note = "ông chủ, ~40 tuổi"
"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".toml", delete=False) as f:
            f.write(toml)
            f.flush()
            glossary = load_glossary(Path(f.name))
            assert glossary is not None
            entry = glossary.characters["John"]
            assert entry.self_ref == "tôi"
            assert entry.address == "anh"
            assert entry.narrator == "anh ấy"
            assert entry.note == "ông chủ, ~40 tuổi"
            Path(f.name).unlink()

    def test_terms(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".toml", delete=False) as f:
            f.write('[terms]\n"machine learning" = "học máy"\n')
            f.flush()
            glossary = load_glossary(Path(f.name))
            assert glossary is not None
            assert glossary.terms["machine learning"] == "học máy"
            Path(f.name).unlink()

    def test_returns_none_for_empty(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".toml", delete=False) as f:
            f.write("[characters]\n")
            f.flush()
            glossary = load_glossary(Path(f.name))
            assert glossary is None
            Path(f.name).unlink()

    def test_returns_none_for_missing_file(self):
        glossary = load_glossary(Path("/nonexistent/glossary.toml"))
        assert glossary is None


class TestCharacterEntry:
    def test_is_empty_for_default(self):
        assert CharacterEntry().is_empty()

    def test_not_empty_with_self_ref(self):
        assert not CharacterEntry(self_ref="tôi").is_empty()

    def test_not_empty_with_address(self):
        assert not CharacterEntry(address="anh").is_empty()


class TestBuildGlossaryPrompt:
    def test_characters_in_prompt(self):
        glossary = Glossary(
            characters={
                "John": CharacterEntry(self_ref="tôi", address="anh", narrator="anh ấy")
            }
        )
        prompt = build_glossary_prompt(glossary)
        assert "John" in prompt
        assert 'self="tôi"' in prompt
        assert 'address="anh"' in prompt
        assert 'narrator="anh ấy"' in prompt

    def test_terms_in_prompt(self):
        glossary = Glossary(terms={"machine learning": "học máy"})
        prompt = build_glossary_prompt(glossary)
        assert "machine learning" in prompt
        assert "học máy" in prompt

    def test_empty_glossary_returns_empty_string(self):
        assert build_glossary_prompt(Glossary()) == ""


class TestValidateGlossary:
    def test_no_warnings_for_valid_glossary(self):
        from trans_epub.config import validate_glossary

        glossary = Glossary(
            characters={"John": CharacterEntry(address="anh")},
            terms={"machine learning": "học máy"},
        )
        warnings = validate_glossary(glossary)
        assert len(warnings) == 0

    def test_warns_on_empty_character(self):
        from trans_epub.config import validate_glossary

        glossary = Glossary(characters={"Ghost": CharacterEntry()})
        warnings = validate_glossary(glossary)
        assert any("Ghost" in w for w in warnings)

    def test_warns_on_empty_term_key(self):
        from trans_epub.config import validate_glossary

        glossary = Glossary(terms={"": "value"})
        warnings = validate_glossary(glossary)
        assert any("empty English" in w for w in warnings)

    def test_warns_on_empty_term_value(self):
        from trans_epub.config import validate_glossary

        glossary = Glossary(terms={"hello": ""})
        warnings = validate_glossary(glossary)
        assert any("hello" in w for w in warnings)

    def test_warns_on_short_term(self):
        from trans_epub.config import validate_glossary

        glossary = Glossary(terms={"a": "một"})
        warnings = validate_glossary(glossary)
        assert any("short" in w.lower() for w in warnings)

    def test_warns_on_character_without_pronouns(self):
        from trans_epub.config import validate_glossary

        # Character with only a note, no address or self-ref
        glossary = Glossary(characters={"Bob": CharacterEntry(note="side character")})
        warnings = validate_glossary(glossary)
        assert any("Bob" in w for w in warnings)


class TestScanGlossaryMatches:
    def test_finds_term_in_text(self):
        from trans_epub.config import scan_glossary_matches

        glossary = Glossary(terms={"hello": "xin chào"})
        matches = scan_glossary_matches(glossary, ["hello world", "say hello"])
        assert matches["hello"] == 2

    def test_case_insensitive_matching(self):
        from trans_epub.config import scan_glossary_matches

        glossary = Glossary(terms={"Hello": "xin chào"})
        matches = scan_glossary_matches(glossary, ["HELLO world", "Say hello"])
        assert matches["Hello"] == 2

    def test_term_not_found_returns_zero(self):
        from trans_epub.config import scan_glossary_matches

        glossary = Glossary(terms={"nonexistent": "không tồn tại"})
        matches = scan_glossary_matches(glossary, ["some text"])
        assert matches["nonexistent"] == 0

    def test_finds_character_name(self):
        from trans_epub.config import scan_glossary_matches

        glossary = Glossary(characters={"Alice": CharacterEntry(address="cô")})
        matches = scan_glossary_matches(
            glossary, ["Alice went to the store", "Bob met Alice"]
        )
        assert matches["[character] Alice"] == 2

    def test_empty_text_no_matches(self):
        from trans_epub.config import scan_glossary_matches

        glossary = Glossary(terms={"hello": "xin chào"})
        matches = scan_glossary_matches(glossary, [])
        assert matches["hello"] == 0
