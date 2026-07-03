"""Quick test to verify all modules can be imported and basic functionality works."""

import sys


def test_imports():
    """Test that all modules can be imported."""
    try:
        import trans_epub
        import trans_epub.cli
        import trans_epub.config
        import trans_epub.engines
        import trans_epub.engines.alibaba
        import trans_epub.engines.azure
        import trans_epub.engines.base
        import trans_epub.engines.deepseek
        import trans_epub.engines.gemini
        import trans_epub.epub_translator
        import trans_epub.html_translator
        import trans_epub.toc  # noqa: F401

        print("✓ All modules imported successfully")
    except ImportError as e:
        print(f"✗ Import error: {e}")
        return False

    return True


def test_version_available():
    """Test that version is available."""
    try:
        import trans_epub

        version = trans_epub.__version__
        assert version is not None
        assert version != "unknown"
        print(f"✓ Version available: {version}")
        return True
    except Exception as e:
        print(f"✗ Version error: {e}")
        return False


def test_engines_registered():
    """Test that engines are properly registered."""
    try:
        from trans_epub.engines import ENGINES

        assert len(ENGINES) > 0
        assert "alibaba" in ENGINES
        assert "azure" in ENGINES
        assert "gemini" in ENGINES
        assert "deepseek" in ENGINES
        print(f"✓ All engines registered: {list(ENGINES.keys())}")
        return True
    except Exception as e:
        print(f"✗ Engine registration error: {e}")
        return False


def run_tests():
    """Run all basic tests."""
    print("Running basic tests...")
    tests = [
        test_imports,
        test_version_available,
        test_engines_registered,
    ]

    all_passed = True
    for test in tests:
        if not test():
            all_passed = False

    if all_passed:
        print("\n✓ All basic tests passed!")
        return True
    else:
        print("\n✗ Some tests failed!")
        return False


if __name__ == "__main__":
    success = run_tests()
    sys.exit(0 if success else 1)
