import json
import os
from pathlib import Path
from typing import Dict

from app.prompts.profiles import DEFAULT_CONTENT_TYPE, ContentType

STATE_FILE = (
    Path(os.environ.get("NOTEBOOKLM_DATA_DIR", "."))
    / ".last_run.json"
)

class StateManager:
    @staticmethod
    def get_state() -> Dict[str, str]:
        """Loads the last run state from the JSON file."""
        if STATE_FILE.exists():
            try:
                with open(STATE_FILE, "r", encoding="utf-8-sig") as f:
                    return json.load(f)
            except Exception:
                return {}
        return {}

    @staticmethod
    def save_state(
        profile_name: str,
        notebook_name: str,
        content_type: ContentType = DEFAULT_CONTENT_TYPE,
    ) -> None:
        """Save the profile, notebook, and selected prompt family."""
        state = {
            "profile_name": profile_name,
            "notebook_name": notebook_name,
            "content_type": content_type,
        }
        with open(STATE_FILE, "w", encoding="utf-8-sig") as f:
            json.dump(state, f, ensure_ascii=False, indent=4)
