"""Shared fixtures for all tests."""

from unittest.mock import patch

import pytest

from trans_epub.engines import ENGINES, EngineConfig


@pytest.fixture
def mock_translate():
    """Default mock translate: prefix each text with 'VI: '."""

    def translate(texts, **_kwargs):
        return [f"VI: {t}" for t in texts]

    return translate


@pytest.fixture
def mock_engine_config(mock_translate):
    """Return a real EngineConfig wired to mock_translate."""
    return EngineConfig(
        name="test",
        translate=mock_translate,
        char_limit=10_000,
        elem_limit=50,
        delay=0,
    )


@pytest.fixture
def mock_engines(mock_engine_config):
    """Patch ENGINES dict so 'test' resolves to mock_engine_config."""
    with patch.dict(ENGINES, {"test": mock_engine_config}):
        yield


@pytest.fixture
def simple_html():
    return b"<html><body><p>Hello world</p></body></html>"
