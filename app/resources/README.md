# Russian morphology references

`russian_morphology.json` is a course-filtered, offline subset of
[OpenRussian's public dictionary](https://en.openrussian.org/dictionary-data),
from <https://github.com/Badestrand/russian-dictionary>. Original field names,
stress marks and inflection cells are retained; German translations and
unrelated lemmas are omitted. The revision is the SHA-256 of the four input
CSV hashes, making refreshes reproducible. Reference data is CC BY-SA 4.0:
<https://creativecommons.org/licenses/by-sa/4.0/>.

OpenCorpora's Russian morphology, bundled by `pymorphy3-dicts-ru`, is used to
check lemma, case and number and propose inflections. Its data is CC BY-SA 3.0:
<https://opencorpora.org/>. The analyzer is pymorphy3 (MIT):
<https://github.com/no-plagiarism/pymorphy3>.

`russian_lexicon_overrides.json` contains reviewed course-specific meanings,
homograph disambiguation, natural number restrictions, stress and corrections
to outdated or malformed reference cells. Corrections include the common
chair/flower/teacher plurals, the fixed stress of контроль, marker as ма́ркер
rather than the billiards term маркёр, and place-specific local-case usages.
The [Gramota dictionary](https://gramota.ru/meta/kontrol) and its
[reference answers](https://gramota.ru/poisk?mode=spravka&query=аэропорт)
are additional checks for the stress and local-case corrections.

The raw cumulative vocabulary remains the authority for inclusion and source
provenance. Neither reference adds unrelated headwords to the exported file.
Arabic transliterations are learner approximations; existing reviewed course
pronunciations take precedence over newly generated ones. Any new unverified
stress or base meaning is retained in the lexicon review queue and blocks final
dictionary export until reviewed. This does not change extraction prompts.

Explicitly reviewed multi-lemma aliases (such as student/studentka) are routed
to separate headwords. Exactly one entry owns the unchanged source record;
other entries link to its source ID. Morphological disambiguation alone never
splits an unfamiliar slash-separated phrase. The modern loans лукум and
маркетплейс use the paradigms in their Russian Wiktionary entries:
<https://ru.wiktionary.org/wiki/лукум> and
<https://ru.wiktionary.org/wiki/маркетплейс> (CC BY-SA 4.0).
The entries for бот (boat), моль (moth), конёк (ice skate), and мак (poppy)
also supply reviewed homonym-specific animacy, gender, and paradigms:
<https://ru.wiktionary.org/wiki/бот>, <https://ru.wiktionary.org/wiki/моль>,
<https://ru.wiktionary.org/wiki/конёк>, <https://ru.wiktionary.org/wiki/мак>.

To refresh references, download the four TSV `.csv` files to a temporary folder,
then run `scripts/build_russian_lexicon.py --reference-csv-dir <folder>
--prepare-only --rebuild` in the app environment. No download occurs at app
runtime. Prepared lexicons can be rendered separately with the document runtime
using `--render-only`; `--sample` produces a small layout proof.

`russian_patterns.py` compresses presentation only. A noun shares a model only
when all endings, natural-number restrictions, gender/animacy, stem alternations
and stress agree. Verbs share one tense/mood at a time, so identical imperatives
cannot imply identical future forms. Original records and complete paradigms
are unchanged; uncertain patterns are shown separately, never forced together.

The new `russian_study.py` layer is a separate presentation index. It links
thematic word entries to complete reference models and retains each differing
form as an exception. Stress rules are abbreviated only when their literal
application reconstructs the reviewed spelling and accent; otherwise the exact
form and its original pronunciation are printed. At most two distinct ending
changes are allowed within one reference family; greater structural differences
receive separate models. Gender/animacy and verb aspect/reflexivity remain
separate. Word number restrictions are explicit. No source or paradigm is edited.
`--layout study` remains available in the optional dictionary builder, as do
`compact` and `expanded`. The Russian app now defaults to the user's original
six-column vocabulary table with lecture numbers, via `russian_flat_vocabulary`.
The table review preserves every source record, fixes reviewed spellings and
learner transcriptions, and conservatively merges attested overlapping rows.
Noun headwords ending in Ь are annotated with (он)/(она) from a reviewed
sense-specific list; infinitives and numerals are not annotated. Original
cumulative state, previous DOCX files, summary and optional dictionaries remain
unchanged. `scripts/build_russian_flat_vocabulary.py` builds a separate reviewed
copy using the original table's package components; provenance and review edits
are retained in `.russian_flat_vocabulary.json` beside the output.
`audit_russian_dictionary_pdf.py --study` checks what is
intentionally printed; `validate_study_index` checks every full hidden form too.
