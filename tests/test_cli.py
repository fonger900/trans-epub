import os
import unittest

import main


class CliTests(unittest.TestCase):
    def test_auto_engine_prefers_available_provider(self):
        original = {k: os.environ.get(k) for k in ["AZURE_TRANSLATOR_KEY", "GEMINI_API_KEY", "DEEPSEEK_API_KEY"]}
        try:
            os.environ.pop("AZURE_TRANSLATOR_KEY", None)
            os.environ["GEMINI_API_KEY"] = "demo"
            os.environ.pop("DEEPSEEK_API_KEY", None)
            self.assertEqual(main.resolve_engine("auto"), "gemini")
        finally:
            for key, value in original.items():
                if value is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = value


if __name__ == "__main__":
    unittest.main()
