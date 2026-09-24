import unittest

from src.web_app.session_token import SessionTokenCodec, SessionTokenError


class SessionTokenTests(unittest.TestCase):
    def setUp(self):
        self.codec = SessionTokenCodec("test-secret-with-enough-length-123456")

    def test_round_trip(self):
        payload = {"motion": "x", "turn": 2, "state": {"propositions": []}}
        token = self.codec.encode(payload)
        self.assertEqual(self.codec.decode(token), payload)

    def test_tamper_is_rejected(self):
        token = self.codec.encode({"turn": 1})
        replacement = ("A" if token[-1] != "A" else "B")
        with self.assertRaises(SessionTokenError):
            self.codec.decode(token[:-1] + replacement)

    def test_empty_secret_is_rejected(self):
        with self.assertRaises(ValueError):
            SessionTokenCodec("")


if __name__ == "__main__":
    unittest.main()
