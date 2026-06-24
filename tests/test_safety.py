import unittest

from voicebot.constants import ALLOWED_DESTINATION
from voicebot.safety import UnsafeDestinationError, normalize_e164, validate_destination


class SafetyTests(unittest.TestCase):
    def test_normalize_e164_accepts_common_formatting(self):
        self.assertEqual(normalize_e164("(805) 439-8008"), ALLOWED_DESTINATION)

    def test_validate_destination_allows_only_test_number(self):
        self.assertEqual(validate_destination("+1-805-439-8008"), ALLOWED_DESTINATION)

    def test_validate_destination_rejects_other_number(self):
        with self.assertRaises(UnsafeDestinationError):
            validate_destination("+18054398009")


if __name__ == "__main__":
    unittest.main()
