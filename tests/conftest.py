"""Test configuration and fixtures."""

import os
import tempfile
from pathlib import Path

import pytest


@pytest.fixture
def temp_dir():
    """Create a temporary directory for tests."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def sample_epub_content():
    """Provide sample EPUB content for testing."""
    return """<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE html>
<html xmlns="http://www.w3.org/1999/xhtml">
<head>
    <title>Sample Chapter</title>
</head>
<body>
    <h1>Chapter 1</h1>
    <p>Hello world!</p>
    <p>This is a test paragraph.</p>
    <div class="note">This note should not be translated.</div>
</body>
</html>"""


@pytest.fixture
def sample_epub_bytes(sample_epub_content):
    """Provide sample EPUB content as bytes."""
    return sample_epub_content.encode("utf-8")
