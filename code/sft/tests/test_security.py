import unittest

from sft.security import scrub


class SecurityTests(unittest.TestCase):
    def test_secret_keys_and_token_like_values_are_redacted(self):
        value = scrub({"apiKey": "do-not-export", "nested": "sk-test_1234567890123", "safe": "hello"})
        self.assertEqual(value["apiKey"], "[REDACTED]")
        self.assertEqual(value["nested"], "[REDACTED]")
        self.assertEqual(value["safe"], "hello")
