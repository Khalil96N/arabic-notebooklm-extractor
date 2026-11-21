# Arabic NotebookLM Extractor

An unofficial local tool for extracting structured Arabic lecture transcripts
from NotebookLM and exporting them as Markdown and editable Word documents.

The tool supports Arabic lectures, English-language courses, and Russian
language courses with separate prompt files selected manually for each
extraction. Russian-course output is reorganized into a fixed review order:
new letters, rules and applications, model dialogues, then the recap and
homework. A separate cumulative vocabulary document keeps every useful
Cyrillic word or phrase with Arabic pronunciation and Arabic and English
meanings. The workflow runs in two
stages. First it asks NotebookLM only for the lecture's
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
Russian and English extraction match each reply to a unique request token,
including retries, so replies from another tab cannot be used as a fallback.
Russian cumulative documents are saved only after all requests finish, in
the original lesson order.

## Usage

### Local Web App

Double-click `start_web_app.bat`, or run:

```bash
python web_app.py
```

The app opens at `http://127.0.0.1:8765`. Enter the exact NotebookLM notebook
name, lecture source name, content type, and browser profile. Chrome opens for
NotebookLM; if
the profile is not signed in, the extraction waits until sign-in is completed
or the web app's **Stop** button is pressed.

The web interface shows live execution logs and provides download links for
the generated Markdown and Word files.

### Command Line

Run the tool via the CLI:
```bash
python main.py --profile account2 --notebook "مقدمات" --lecture "اسم المحاضرة"
```

Use `--content-type english` for an English course or `--content-type russian`
for a Russian course. The default is `--content-type arabic`.

Optional book/source context can be added with `--book "اسم الكتاب"`.

### First Time Run (Login Required)
On the very first run, Playwright will open a Chromium window and navigate to NotebookLM. You may be prompted to log in to your Google Account.
The script will wait for a bit to allow you to log in. Once logged in, the session is saved in `browser_data/` so subsequent runs will be automated.

## Output Structure
The extracted files are saved in the local `output/` directory:
- `<lecture>.md`: The final transcript assembled from the separate detailed extractions.
- `<lecture>.docx`: The formatted Word version of the assembled transcript.
- Russian courses instead update two cumulative Word files: the existing summary
  for lectures `1-N` and `قاموس مفردات اللغة الروسية - نسخة الحفظ - المحاضرات 1-N.docx`.
  The dictionary groups verbs by infinitive and nouns by base form, with Arabic
  pronunciation, Arabic/English meanings, and no visible lecture-number column.
  Word starts with four-column thematic study tables. Each basic entry occurs
  once and links to shared models in a final inflection appendix. Spelling/stem
  exceptions appear beside the word; exact stress-only differences can use short
  explicit rules instead of another complete table. Every full form must be
  reconstructible from its model and exceptions before publication. Verb models
  remain independent per tense/mood; indeclinables have a label, not a repeated
  twelve-cell table. Full paradigms and provenance remain in the internal cache.
  Older dictionaries/flat tables are not overwritten. The earlier grouped layout
  is available with `scripts/build_russian_lexicon.py --render-only --layout compact`
  and the full per-word layout with `--layout expanded`; the default is `study`.

The raw cumulative state stays in `.russian_course_cumulative.json`. A separate
`.russian_lexicon.json` stores the derived entries, original records, source links
and morphology review queue. New uncertain base meanings or pronunciation stress
block dictionary publication rather than inventing an answer; the extraction is
still preserved for review. See `app/resources/README.md` for references, licences
and the offline rebuild commands. Russian extraction prompts, summaries and the
Arabic/English workflows are not changed by this dictionary layer.

The extraction plan (`transcript.txt`, `headings.txt`) and generated prompts
(`section_prompts.md`) are temporary. The app removes them after a successful
run. If extraction fails, it keeps them in `output/` for diagnosis or resume.
Existing QA render folders under `.work_transcripts/` are separate development
artifacts; the app does not create or automatically delete those folders.

## Project Structure

- `app/workflow.py`: end-to-end extraction workflow.
- `app/services/notebooklm.py`: extraction-plan discovery and section-extraction facade.
- `app/services/notebooklm_page.py`: browser navigation, source selection, and response reading.
- `app/services/retry_button.py`: automatic NotebookLM Retry/Try again button handling.
- `app/services/section_extractor.py`: parallel section extraction and retries.
- `app/prompts/arabic_lecture_templates.py`: Arabic lecture prompts.
- `app/prompts/english_course_templates.py`: English course prompts.
- `app/prompts/russian_course_templates.py`: Russian course prompts with
  fixed summary sections and a separate vocabulary extraction schema.
- `app/prompts/generator.py`: builds one prompt per heading or final question.
- `app/exporters/text.py`: transcript, headings, prompts, and Markdown output.
- `app/exporters/word.py`: Word document rendering.
- `app/exporters/russian_course.py`: cumulative Russian summary and dictionary
  export integration, with the legacy flat-table renderer retained separately.
- `app/services/russian_lexicon.py`: source-preserving lemma grouping, morphology,
  semantic families and reviewed reference data.
- `app/exporters/russian_lexicon.py`: preserved compact/expanded layouts and
  dispatch to the linked study layout in `russian_study.py`.
- `app/exporters/file.py`: backward-compatible exporter facade.
- `web_app.py`: local HTTP server and extraction job manager.
- `web/`: local browser interface.

## Privacy Notes

This project stores browser session data locally in `browser_data/` so you do
not need to sign in every run. That folder is intentionally ignored by Git and
must not be committed or shared. Generated lecture files in `output/` are also
ignored.
