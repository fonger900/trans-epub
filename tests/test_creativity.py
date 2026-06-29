import os
import unittest

import main


class DummyResponse:
    def __init__(self, payload):
        self.payload = payload
        self.status_code = 200

    def raise_for_status(self):
        return None

    def json(self):
        return self.payload


class RecordingSession:
    def __init__(self, payload):
        self.payload = payload
        self.calls = []

    def post(self, url, **kwargs):
        self.calls.append((url, kwargs))
        return DummyResponse(self.payload)


class CreativityTests(unittest.TestCase):
    def test_gemini_translate_forwards_temperature(self):
        original_env = os.environ.get("GEMINI_API_KEY")
        original_session = main.http_session
        session = RecordingSession(
            {"candidates": [{"content": {"parts": [{"text": '{"translations":["Xin chao"]}'}]}}]}
        )
        os.environ["GEMINI_API_KEY"] = "demo"
        main.http_session = session
        try:
            result = main.gemini_translate(["Hello"], creativity=0.9)
        finally:
            main.http_session = original_session
            if original_env is None:
                os.environ.pop("GEMINI_API_KEY", None)
            else:
                os.environ["GEMINI_API_KEY"] = original_env

        self.assertEqual(result, ["Xin chao"])
        self.assertEqual(session.calls[0][1]["json"]["generationConfig"]["temperature"], 0.9)

    def test_deepseek_translate_forwards_temperature(self):
        original_env = os.environ.get("DEEPSEEK_API_KEY")
        original_session = main.http_session
        session = RecordingSession({"choices": [{"message": {"content": '{"translations":["Xin chao"]}'}}]})
        os.environ["DEEPSEEK_API_KEY"] = "demo"
        main.http_session = session
        try:
            result = main.deepseek_translate(["Hello"], creativity=0.2)
        finally:
            main.http_session = original_session
            if original_env is None:
                os.environ.pop("DEEPSEEK_API_KEY", None)
            else:
                os.environ["DEEPSEEK_API_KEY"] = original_env

        self.assertEqual(result, ["Xin chao"])
        self.assertEqual(session.calls[0][1]["json"]["temperature"], 0.2)


if __name__ == "__main__":
    unittest.main()
