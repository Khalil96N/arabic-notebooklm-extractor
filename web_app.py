import argparse
import json
import mimetypes
import os
import re
import subprocess
import sys
import threading
import webbrowser
from datetime import datetime
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, quote, unquote, urlparse

FROZEN = bool(getattr(sys, "frozen", False))
RESOURCE_ROOT = (
    Path(getattr(sys, "_MEIPASS"))
    if FROZEN
    else Path(__file__).resolve().parent
)
DATA_ROOT = (
    Path(os.environ.get("LOCALAPPDATA", Path.home()))
    / "NotebookLMExtractor"
    if FROZEN
    else RESOURCE_ROOT
)
DATA_ROOT.mkdir(parents=True, exist_ok=True)
os.environ["NOTEBOOKLM_DATA_DIR"] = str(DATA_ROOT)

from app.config.state import StateManager
from app.prompts.profiles import DEFAULT_CONTENT_TYPE, validate_content_type


WEB_ROOT = RESOURCE_ROOT / "web"
OUTPUT_DIR = DATA_ROOT / "output"
MAIN_SCRIPT = RESOURCE_ROOT / "main.py"
VENV_PYTHON = RESOURCE_ROOT / "venv" / "Scripts" / "python.exe"
ANSI_ESCAPE = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]")
ALLOWED_DOWNLOAD_EXTENSIONS = {".md", ".docx", ".txt"}


def extraction_python() -> Path:
    return VENV_PYTHON if VENV_PYTHON.exists() else Path(sys.executable)


def build_extraction_command(
    profile_name: str,
    notebook_name: str,
    lecture_name: str,
    content_type: str = DEFAULT_CONTENT_TYPE,
    book_name: str = "",
) -> list[str]:
    content_type = validate_content_type(content_type)
    executable = (
        [str(Path(sys.executable).with_name("NotebookLMWorker.exe"))]
        if FROZEN
        else [str(extraction_python()), str(MAIN_SCRIPT)]
    )
    command = executable + [
        "--profile",
        profile_name,
        "--notebook",
        notebook_name,
        "--lecture",
        lecture_name,
        "--content-type",
        content_type,
    ]
    if book_name:
        command += ["--book", book_name]
    return command


def output_file_from_name(name: str) -> Path | None:
    decoded_name = unquote(name)
    if (
        not decoded_name
        or decoded_name != Path(decoded_name).name
        or Path(decoded_name).suffix.lower() not in ALLOWED_DOWNLOAD_EXTENSIONS
    ):
        return None

    output_root = OUTPUT_DIR.resolve()
    candidate = (OUTPUT_DIR / decoded_name).resolve()
    if candidate.parent != output_root or not candidate.is_file():
        return None
    return candidate


def list_output_files(limit: int = 20) -> list[dict]:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    files = [
        path
        for path in OUTPUT_DIR.iterdir()
        if path.is_file()
        and path.suffix.lower() in ALLOWED_DOWNLOAD_EXTENSIONS
        and not path.name.startswith("~$")
        and path.name not in {
            "transcript.txt",
            "headings.txt",
            "section_prompts.md",
        }
    ]
    files.sort(key=lambda path: path.stat().st_mtime, reverse=True)
    return [
        {
            "name": path.name,
            "extension": path.suffix.lower().lstrip("."),
            "size": path.stat().st_size,
            "modified_at": datetime.fromtimestamp(
                path.stat().st_mtime
            ).isoformat(timespec="seconds"),
            "download_url": f"/api/download?name={path.name}",
        }
        for path in files[:limit]
    ]


class JobManager:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._process: subprocess.Popen | None = None
        self._worker: threading.Thread | None = None
        self._logs: list[dict] = []
        self._next_log_id = 1
        self._status = "idle"
        self._started_at: str | None = None
        self._finished_at: str | None = None
        self._return_code: int | None = None
        self._profile_name = ""
        self._notebook_name = ""
        self._lecture_name = ""
        self._book_name = ""
        self._content_type = DEFAULT_CONTENT_TYPE
        self._stopping = False

    def start(
        self,
        profile_name: str,
        notebook_name: str,
        lecture_name: str,
        content_type: str = DEFAULT_CONTENT_TYPE,
        book_name: str = "",
    ) -> dict:
        profile_name = profile_name.strip() or "default"
        notebook_name = notebook_name.strip()
        lecture_name = lecture_name.strip()
        book_name = book_name.strip()
        content_type = validate_content_type(content_type)
        if not notebook_name or not lecture_name:
            raise ValueError("اسم الدفتر واسم المحاضرة مطلوبان.")

        with self._lock:
            if self._process and self._process.poll() is None:
                raise RuntimeError("هناك مهمة استخراج تعمل بالفعل.")

            self._logs = []
            self._next_log_id = 1
            self._status = "starting"
            self._started_at = datetime.now().isoformat(timespec="seconds")
            self._finished_at = None
            self._return_code = None
            self._profile_name = profile_name
            self._notebook_name = notebook_name
            self._lecture_name = lecture_name
            self._book_name = book_name
            self._content_type = content_type
            self._stopping = False
            self._append_log_unlocked(
                "بدء المهمة. سيفتح Chrome تلقائيًا. إذا طُلب تسجيل الدخول، "
                "أكمله في نافذة Chrome."
            )

            StateManager.save_state(
                profile_name,
                notebook_name,
                content_type,
            )
            self._worker = threading.Thread(
                target=self._run,
                args=(
                    profile_name,
                    notebook_name,
                    lecture_name,
                    content_type,
                    book_name,
                ),
                daemon=True,
            )
            self._worker.start()
            return self._snapshot_unlocked(after=0)

    def stop(self) -> dict:
        with self._lock:
            process = self._process
            if not process or process.poll() is not None:
                return self._snapshot_unlocked(after=0)
            self._stopping = True
            self._status = "stopping"
            self._append_log_unlocked("جارٍ إيقاف المهمة وإغلاق المتصفح...")

        if os.name == "nt":
            subprocess.run(
                [
                    "taskkill",
                    "/PID",
                    str(process.pid),
                    "/T",
                    "/F",
                ],
                capture_output=True,
                creationflags=subprocess.CREATE_NO_WINDOW,
                check=False,
            )
        else:
            process.terminate()
        return self.snapshot()

    def snapshot(self, after: int = 0) -> dict:
        with self._lock:
            return self._snapshot_unlocked(after)

    def _run(
        self,
        profile_name: str,
        notebook_name: str,
        lecture_name: str,
        content_type: str,
        book_name: str = "",
    ) -> None:
        environment = os.environ.copy()
        environment.update(
            {
                "PYTHONUTF8": "1",
                "PYTHONIOENCODING": "utf-8",
                "NO_COLOR": "1",
                "COLUMNS": "220",
            }
        )
        creation_flags = (
            subprocess.CREATE_NO_WINDOW | subprocess.CREATE_NEW_PROCESS_GROUP
            if os.name == "nt"
            else 0
        )

        try:
            process = subprocess.Popen(
                build_extraction_command(
                    profile_name,
                    notebook_name,
                    lecture_name,
                    content_type,
                    book_name,
                ),
                cwd=DATA_ROOT,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
                bufsize=1,
                env=environment,
                creationflags=creation_flags,
            )
            with self._lock:
                self._process = process
                self._status = "running"

            assert process.stdout is not None
            for line in process.stdout:
                clean_line = ANSI_ESCAPE.sub("", line).rstrip()
                if clean_line:
                    with self._lock:
                        self._append_log_unlocked(clean_line)
                        self._update_status_from_line_unlocked(clean_line)

            return_code = process.wait()
            with self._lock:
                self._return_code = return_code
                self._finished_at = datetime.now().isoformat(timespec="seconds")
                if self._stopping:
                    self._status = "stopped"
                    self._append_log_unlocked("تم إيقاف المهمة.")
                elif return_code == 0:
                    self._status = "completed"
                    self._append_log_unlocked("اكتملت المهمة بنجاح.")
                else:
                    self._status = "failed"
                    self._append_log_unlocked(
                        "فشلت المهمة. راجع السجل لمعرفة السبب."
                    )
                self._process = None
        except Exception as exc:
            with self._lock:
                self._status = "failed"
                self._finished_at = datetime.now().isoformat(timespec="seconds")
                self._return_code = 1
                self._process = None
                self._append_log_unlocked(f"تعذر تشغيل المهمة: {exc}")

    def _update_status_from_line_unlocked(self, line: str) -> None:
        lowered = line.casefold()
        if "login required" in lowered or "still waiting for login" in lowered:
            self._status = "waiting_for_login"
        elif "already logged in" in lowered or "login detected" in lowered:
            self._status = "extracting"
        elif "starting phase 2" in lowered:
            self._status = "extracting_sections"
        elif "workflow completed successfully" in lowered:
            self._status = "finalizing"

    def _append_log_unlocked(self, message: str) -> None:
        self._logs.append(
            {
                "id": self._next_log_id,
                "time": datetime.now().strftime("%H:%M:%S"),
                "message": message,
            }
        )
        self._next_log_id += 1
        if len(self._logs) > 2500:
            self._logs = self._logs[-2000:]

    def _snapshot_unlocked(self, after: int) -> dict:
        logs = [entry for entry in self._logs if entry["id"] > after]
        return {
            "status": self._status,
            "started_at": self._started_at,
            "finished_at": self._finished_at,
            "return_code": self._return_code,
            "profile_name": self._profile_name,
            "notebook_name": self._notebook_name,
            "lecture_name": self._lecture_name,
            "book_name": self._book_name,
            "content_type": self._content_type,
            "can_start": not (
                self._process and self._process.poll() is None
            ),
            "can_stop": bool(
                self._process and self._process.poll() is None
            ),
            "logs": logs,
            "last_log_id": self._logs[-1]["id"] if self._logs else 0,
            "files": list_output_files(),
        }


JOB_MANAGER = JobManager()


class NotebookLMWebHandler(BaseHTTPRequestHandler):
    server_version = "NotebookLMWeb/1.0"

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path == "/api/state":
            state = StateManager.get_state()
            self._send_json(
                {
                    "defaults": {
                        "profile_name": state.get(
                            "profile_name",
                            "account2",
                        ),
                        "notebook_name": state.get("notebook_name", ""),
                        "content_type": state.get(
                            "content_type",
                            DEFAULT_CONTENT_TYPE,
                        ),
                    },
                    "job": JOB_MANAGER.snapshot(),
                }
            )
            return

        if parsed.path == "/api/jobs/current":
            query = parse_qs(parsed.query)
            try:
                after = max(0, int(query.get("after", ["0"])[0]))
            except ValueError:
                after = 0
            self._send_json(JOB_MANAGER.snapshot(after=after))
            return

        if parsed.path == "/api/files":
            self._send_json({"files": list_output_files()})
            return

        if parsed.path == "/api/download":
            name = parse_qs(parsed.query).get("name", [""])[0]
            file_path = output_file_from_name(name)
            if not file_path:
                self.send_error(HTTPStatus.NOT_FOUND)
                return
            self._send_file(file_path, attachment=True)
            return

        if parsed.path == "/favicon.ico":
            self.send_response(HTTPStatus.NO_CONTENT)
            self.end_headers()
            return

        static_path = "index.html" if parsed.path == "/" else parsed.path.lstrip("/")
        file_path = (WEB_ROOT / static_path).resolve()
        if (
            file_path.parent != WEB_ROOT.resolve()
            and WEB_ROOT.resolve() not in file_path.parents
        ) or not file_path.is_file():
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        self._send_file(file_path)

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        try:
            payload = self._read_json()
        except (ValueError, json.JSONDecodeError):
            self._send_json({"error": "طلب غير صالح."}, status=400)
            return

        if parsed.path == "/api/jobs":
            try:
                job = JOB_MANAGER.start(
                    payload.get("profile_name", ""),
                    payload.get("notebook_name", ""),
                    payload.get("lecture_name", ""),
                    payload.get("content_type", DEFAULT_CONTENT_TYPE),
                    payload.get("book_name", ""),
                )
            except ValueError as exc:
                self._send_json({"error": str(exc)}, status=400)
                return
            except RuntimeError as exc:
                self._send_json({"error": str(exc)}, status=409)
                return
            self._send_json(job, status=202)
            return

        if parsed.path == "/api/jobs/current/stop":
            self._send_json(JOB_MANAGER.stop())
            return

        self.send_error(HTTPStatus.NOT_FOUND)

    def _read_json(self) -> dict:
        length = int(self.headers.get("Content-Length", "0"))
        if length <= 0 or length > 100_000:
            raise ValueError("Invalid body length")
        return json.loads(self.rfile.read(length).decode("utf-8"))

    def _send_json(self, payload: dict, status: int = 200) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _send_file(self, path: Path, attachment: bool = False) -> None:
        body = path.read_bytes()
        content_type = mimetypes.guess_type(path.name)[0]
        content_type = content_type or "application/octet-stream"
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        if attachment:
            safe_name = path.name.replace('"', "")
            self.send_header(
                "Content-Disposition",
                f"attachment; filename*=UTF-8''{quote(safe_name)}",
            )
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args) -> None:
        return


def create_server(host: str, port: int) -> ThreadingHTTPServer:
    server = ThreadingHTTPServer((host, port), NotebookLMWebHandler)
    server.daemon_threads = True
    return server


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run the local NotebookLM extraction web app."
    )
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--no-browser", action="store_true")
    args = parser.parse_args()

    os.chdir(DATA_ROOT)
    server = create_server(args.host, args.port)
    url = f"http://{args.host}:{server.server_address[1]}"
    print(f"NotebookLM web app is running at {url}")
    print("Press Ctrl+C to stop the server.")
    if not args.no_browser:
        threading.Timer(0.8, lambda: webbrowser.open(url)).start()

    try:
        server.serve_forever(poll_interval=0.3)
    except KeyboardInterrupt:
        pass
    finally:
        JOB_MANAGER.stop()
        server.server_close()


if __name__ == "__main__":
    main()
