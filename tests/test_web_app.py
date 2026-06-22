import json
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.request import urlopen

import web_app


class WebAppTests(unittest.TestCase):
    def test_extraction_command_preserves_exact_names(self):
        command = web_app.build_extraction_command(
            "account2",
            "دفتر العقيدة",
            "الفصل (2,3,4) - العقيدة 16.mp4",
        )

        self.assertEqual(str(web_app.MAIN_SCRIPT), command[1])
        self.assertEqual(
            [
                "--profile",
                "account2",
                "--notebook",
                "دفتر العقيدة",
                "--lecture",
                "الفصل (2,3,4) - العقيدة 16.mp4",
            ],
            command[2:],
        )

    def test_download_path_rejects_traversal(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            output_dir = Path(temp_dir)
            valid_file = output_dir / "نتيجة.md"
            valid_file.write_text("ok", encoding="utf-8")

            with patch.object(web_app, "OUTPUT_DIR", output_dir):
                self.assertEqual(
                    valid_file.resolve(),
                    web_app.output_file_from_name("نتيجة.md"),
                )
                self.assertIsNone(
                    web_app.output_file_from_name("../نتيجة.md")
                )
                self.assertIsNone(
                    web_app.output_file_from_name("نتيجة.exe")
                )

    def test_output_list_ignores_word_lock_files(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            output_dir = Path(temp_dir)
            (output_dir / "نتيجة.docx").write_bytes(b"docx")
            (output_dir / "~$نتيجة.docx").write_bytes(b"lock")

            with patch.object(web_app, "OUTPUT_DIR", output_dir):
                names = [
                    item["name"] for item in web_app.list_output_files()
                ]

        self.assertEqual(["نتيجة.docx"], names)

    def test_job_requires_notebook_and_lecture_names(self):
        manager = web_app.JobManager()

        with self.assertRaises(ValueError):
            manager.start("account2", "", "محاضرة")
        with self.assertRaises(ValueError):
            manager.start("account2", "دفتر", "")

    def test_server_exposes_home_and_state_api(self):
        server = web_app.create_server("127.0.0.1", 0)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        base_url = f"http://127.0.0.1:{server.server_address[1]}"
        try:
            with urlopen(f"{base_url}/", timeout=5) as response:
                page = response.read().decode("utf-8")
            with urlopen(f"{base_url}/api/state", timeout=5) as response:
                state = json.loads(response.read().decode("utf-8"))
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)

        self.assertIn("مستخرج محاضرات NotebookLM", page)
        self.assertIn("defaults", state)
        self.assertIn("job", state)


if __name__ == "__main__":
    unittest.main()
