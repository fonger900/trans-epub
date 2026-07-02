"""Tests for the CLI module."""

import subprocess
import sys
from unittest.mock import MagicMock, patch

import pytest

from trans_epub.cli import __version__, main


def test_version_flag():
    """Test that --version flag works."""
    with pytest.raises(SystemExit) as exc_info:
        main(["--version"])

    # The version command should exit with code 0
    assert exc_info.value.code == 0


def test_version_variable():
    """Test that version variable is properly set."""
    assert __version__ is not None
    assert __version__ != "unknown"
    assert isinstance(__version__, str)


def test_main_returns_int():
    """Test that main function exits with error code when no input given."""
    # main([]) exits with code 2 because 'input' is a required positional arg
    with pytest.raises(SystemExit) as exc_info:
        main([])

    assert exc_info.value.code == 2
