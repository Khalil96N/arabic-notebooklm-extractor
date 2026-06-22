# Arabic NotebookLM Extractor

An unofficial local tool for extracting structured Arabic lecture transcripts
from NotebookLM and exporting them as Markdown and editable Word documents.

The workflow runs in two stages. First it asks NotebookLM only for the lecture's
broad extraction plan. Then it requests every main section and end-of-lesson
question separately before assembling the final Markdown and `.docx` outputs.

The extractor also watches for NotebookLM's `Retry` / `Try again` button while
waiting for a response and clicks it automatically when NotebookLM gets stuck.

## Requirements
- Python 3.11+
- Google Chrome installed locally

## Installation

1. Create a virtual environment:
   ```bash
   python -m venv venv
   # On Windows
   venv\Scripts\activate
   # On Linux/macOS
   source venv/bin/activate
   ```

2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   playwright install chromium
   ```

3. Configure Environment Variables:
   Copy `.env.example` to `.env` and adjust if needed:
   ```bash
   cp .env.example .env
   ```

`PARALLEL_EXTRACTIONS` controls how many NotebookLM tabs work simultaneously
inside the same Chrome window. NotebookLM disables the active tab's query box
while it responds, so separate tabs are used for parallel extraction. The
default is `3`; reduce it to `1` for fully sequential extraction.

## Usage

### Local Web App

Double-click `start_web_app.bat`, or run:

```bash
python web_app.py
```

The app opens at `http://127.0.0.1:8765`. Enter the exact NotebookLM notebook
name, lecture source name, and browser profile. Chrome opens for NotebookLM; if
the profile is not signed in, the extraction waits until sign-in is completed
or the web app's **Stop** button is pressed.

The web interface shows live execution logs and provides download links for
the generated Markdown and Word files.

### Command Line

Run the tool via the CLI:
```bash
python main.py --profile account2 --notebook "مقدمات" --lecture "اسم المحاضرة"
```

Optional book/source context can be added with `--book "اسم الكتاب"`.

### First Time Run (Login Required)
On the very first run, Playwright will open a Chromium window and navigate to NotebookLM. You may be prompted to log in to your Google Account.
The script will wait for a bit to allow you to log in. Once logged in, the session is saved in `browser_data/` so subsequent runs will be automated.

## Output Structure
The extracted files are saved in the local `output/` directory:
- `transcript.txt`: The phase-one extraction-plan response (legacy diagnostic filename).
- `headings.txt`: The parsed extraction items (legacy diagnostic filename).
- `section_prompts.md`: The generated Arabic prompts for each individual section.
- `<lecture>.md`: The final transcript assembled from the separate detailed extractions.
- `<lecture>.docx`: The formatted Word version of the assembled transcript.

## Project Structure

- `app/workflow.py`: end-to-end extraction workflow.
- `app/services/notebooklm.py`: extraction-plan discovery and section-extraction facade.
- `app/services/notebooklm_page.py`: browser navigation, source selection, and response reading.
- `app/services/retry_button.py`: automatic NotebookLM Retry/Try again button handling.
- `app/services/section_extractor.py`: parallel section extraction and retries.
- `app/prompts/templates.py`: all NotebookLM prompt text.
- `app/prompts/generator.py`: builds one prompt per heading or final question.
- `app/exporters/text.py`: transcript, headings, prompts, and Markdown output.
- `app/exporters/word.py`: Word document rendering.
- `app/exporters/file.py`: backward-compatible exporter facade.
- `web_app.py`: local HTTP server and extraction job manager.
- `web/`: local browser interface.

## Privacy Notes

This project stores browser session data locally in `browser_data/` so you do
not need to sign in every run. That folder is intentionally ignored by Git and
must not be committed or shared. Generated lecture files in `output/` are also
ignored.
