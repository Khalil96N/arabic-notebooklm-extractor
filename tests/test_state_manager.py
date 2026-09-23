import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.config.state import StateManager


class StateManagerTests(unittest.TestCase):
    def test_state_file_round_trips_arabic_with_windows_friendly_bom(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            state_file = Path(temp_dir) / ".last_run.json"
            with patch("app.config.state.STATE_FILE", state_file):
                StateManager.save_state("account2", "مقدمات")
                loaded_state = StateManager.get_state()

            raw_bytes = state_file.read_bytes()

        self.assertTrue(raw_bytes.startswith(b"\xef\xbb\xbf"))
        self.assertEqual(
            {
                "profile_name": "account2",
                "notebook_name": "مقدمات",
                "content_type": "arabic",
            },
            loaded_state,
        )

    def test_state_file_remembers_english_content_type(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            state_file = Path(temp_dir) / ".last_run.json"
            with patch("app.config.state.STATE_FILE", state_file):
                StateManager.save_state("account2", "Course", "english")
                loaded_state = StateManager.get_state()

        self.assertEqual("english", loaded_state["content_type"])


if __name__ == "__main__":
    unittest.main()
