import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from voicebot.config import load_settings


class ConfigTests(unittest.TestCase):
    def test_blank_environment_value_does_not_mask_dotenv_value(self):
        with tempfile.NamedTemporaryFile("w", delete=False, encoding="utf-8") as env_file:
            env_file.write("PUBLIC_BASE_URL=https://current-tunnel.example\n")
            env_path = env_file.name

        try:
            with patch.dict(os.environ, {"PUBLIC_BASE_URL": "   "}, clear=True):
                settings = load_settings(env_path)
        finally:
            Path(env_path).unlink(missing_ok=True)

        self.assertEqual(settings.public_base_url, "https://current-tunnel.example")


if __name__ == "__main__":
    unittest.main()
