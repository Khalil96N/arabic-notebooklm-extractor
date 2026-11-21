"""NotebookLM prompts for cumulative Russian-course study notes.

Russian lessons are reorganized into a stable review order (letters, rules,
dialogues, then a recap) instead of being exported as a verbatim classroom
transcript, and vocabulary is extracted alongside them so it never appears as
a duplicate table in the summary.

Each lesson is first split into small chronological chunks (the same
boundary-hint mechanism used for the Arabic/English profiles). A single
request that asks NotebookLM to scan an entire long recording in one shot has
been observed to invent content from a neighbouring source instead of
reporting that it found nothing new, so every extraction call here stays
scoped to one small, explicitly-bounded slice of the lesson. To keep the
number of NotebookLM calls down, all four buckets for one chunk are requested
in a single combined prompt (see CHUNK_PROMPT_TEMPLATE) and then split apart
locally with `split_chunk_response`, instead of four separate calls per
chunk.
"""

import re
from collections.abc import Iterable


OUTLINE_PROMPT_TEMPLATE = """حلّل مصدر درس اللغة الروسية المحدد فقط: ({lecture_name}).
هذه مرحلة تخطيط فقط؛ لا تكتب التفريغ الكامل الآن.

المطلوب:
1- قسّم الدرس إلى أقسام تعليمية متتابعة حسب ترتيب الشرح الفعلي.
2- اجعل كل قسم صغيراً بما يكفي لاستخراج جميع حروفه وقواعده وحواراته في طلب مستقل، وغالباً يغطي 3-6 دقائق من المادة.
3- اكتب عنوان كل قسم بالعربية، وأبقِ الحروف أو الكلمات الروسية المحورية داخل العنوان كما ظهرت في المصدر.
4- ركّز التقسيم على شرح المدرّس وقراءته النموذجية والقواعد والأمثلة الجديدة. لا تنشئ أقساماً مستقلة لحضور الطلاب أو مشكلات الميكروفون أو قراءة كل طالب أو ترديد المجموعة أو المحاولات الفردية المتكررة.
5- إذا أعاد الطلاب الحروف أو الكلمات بعد المدرّس، اعتبر ذلك تدريباً صفياً داخل القسم نفسه، ولا توسّع له حدوداً أو عناوين جديدة.
6- لكل قسم اكتب عبارة بداية وعبارة نهاية واضحتين من كلام المصدر نفسه، بالعربية أو الروسية بحسب ما هو مسموع، ولا تجعلها شرحاً من عندك.
7- لا تستخدم الأقواس المزدوجة [[...]] إلا للوسوم التالية فقط.

الصيغة الإلزامية:
[[رئيسي: أولاً: عنوان القسم الأول، مع الحرف الروسي إن وجد]]
[[بداية: أول عبارة واضحة يبدأ عندها القسم]]
[[نهاية: آخر عبارة واضحة ينتهي عندها القسم قبل القسم التالي]]
[[رئيسي: ثانياً: عنوان القسم الثاني، مع الحرف الروسي إن وجد]]
[[بداية: أول عبارة واضحة يبدأ عندها القسم]]
[[نهاية: آخر عبارة واضحة ينتهي عندها القسم]]

استمر حتى نهاية الدرس، ولا تتوقف قبل آخر جملة مسموعة في التسجيل.
لا تكتب مقدمة أو خاتمة أو محتوى خارج الوسوم.
"""


SECTION_BOUNDARY_TEMPLATE = """
ابدأ عند «{start_hint}» وانته عند «{end_hint}». التزم بهذا الجزء فقط."""


CHUNK_PROMPT_TEMPLATE = """استخرج الجزء المحدد من الروسية في أربعة أقسام:
{boundary_context}
اعتمد المعلمة مرة واحدة؛ احذف تكرار الطلاب وأسماء الطلاب والإدارة والحضور ومشكلات الاتصال. لا تخترع. لكل نص روسي لفظ عربي ومعنى عربي (P=پ V=ڤ G=گ). بلا جداول. حافظ على الوسوم والأقسام حتى إن كانت فارغة:

<letters_section>
الحروف الجديدة فقط: <subheading>الحرف</subheading><russian>كبير وصغير</russian><pronunciation>الاسم والصوت بالعربي</pronunciation><translation>وصف الصوت والفرق عن المشابه</translation>. بلا رسم أو سلاسل تدريب، وأمثلة نطق قليلة عند الحاجة.
</letters_section>

<rules_section>
<subheading>القاعدة</subheading> شرح عربي ومتى تستخدم، و2–4 أمثلة من التسجيل: <russian>...</russian><pronunciation>...</pronunciation><translation>...</translation>. للمكرر اكتب مراجعة وأضف الجديد فقط. {review_context}
</rules_section>

<dialogues_section>
نموذج المعلمة بلا تكرار: <speaker>A</speaker><russian>...</russian><pronunciation>...</pronunciation><translation>...</translation>. المتحدثان A وB دون أسماء.
</dialogues_section>

<vocabulary_section>
كل الكلمات والعبارات المفيدة من نص الدرس ومن كلام المعلمة الروسي أثناء الشرح، حتى إن لم تقرأها من النص؛ تشمل تعليمات الصف والحوار. استبعد الكلام الإداري وتكرار الطلاب والمقاطع بلا معنى. العبارة كاملة والكلمات ذات المعنى المستقل، دون تكرار. لكل مدخل: <vocabulary_item><category>مجموعة موضوعية</category><russian>...</russian><pronunciation>...</pronunciation><translation>...</translation><english>...</english></vocabulary_item>.
</vocabulary_section>"""

# Leave room for the strict response-ID wrapper added by SectionExtractor.
MAX_CHUNK_PROMPT_CHARACTERS = 1800


RECAP_PROMPT_TEMPLATE = """استخرج من الجزء الأخير من تسجيل درس اللغة الروسية المحدد الخلاصة والواجب فقط.
{boundary_context}

ابدأ بـ <subheading>الخلاصة والواجب</subheading>، ثم اكتب:
- أهم ما يجب تذكره من الحروف والقواعد في نقاط قصيرة.
- الواجب المتعلق بتعلم الروسية إن طلبته المعلمة.
- أي تنبيه دراسي عام لازم لتنفيذ الواجب.

لا تنشئ قائمة كلمات أو جدول مفردات. لا تكرر أمثلة الأقسام السابقة، ولا تذكر حضور
الطلاب أو الاستراحة أو مشكلات الاتصال أو البريد والعناوين الشخصية أو الحديث الإداري.
إذا لم يوجد واجب واضح، اكتب: لم يُذكر واجب دراسي واضح في هذا التسجيل.
لا تضف معلومات من خارج المصدر ولا تكتب سؤال متابعة.
"""


END_QUESTION_PROMPT_TEMPLATE = RECAP_PROMPT_TEMPLATE


def build_outline_prompt(
    lecture_name: str,
    book_name: str | None = None,
) -> str:
    """Build the chronological chunking plan for one selected Russian lesson."""
    del book_name  # Russian course prompts intentionally target the lesson only.
    return OUTLINE_PROMPT_TEMPLATE.format(lecture_name=lecture_name)


def build_boundary_context(
    start_hint: str | None,
    end_hint: str | None,
) -> str:
    """Build the exact source boundaries used by one Russian lesson chunk."""
    if not (start_hint or end_hint):
        return ""

    return SECTION_BOUNDARY_TEMPLATE.format(
        start_hint=(start_hint[:150] if start_hint else "غير محددة"),
        end_hint=(end_hint[-150:] if end_hint else "غير محددة"),
    )


def build_chunk_prompt(
    boundary_context: str,
    prior_rule_names: Iterable[str] = (),
) -> tuple[str, str, str]:
    """Return the single combined prompt covering all four buckets for one chunk."""
    rule_names = [name.strip() for name in prior_rule_names if name.strip()]
    context_prefix = "قواعد سابقة: "
    base_length = len(CHUNK_PROMPT_TEMPLATE.format(
        boundary_context=boundary_context, review_context="",
    ))
    context_budget = max(0, MAX_CHUNK_PROMPT_CHARACTERS - base_length - len(context_prefix))
    if rule_names:
        selected_names = []
        used_characters = 0
        for name in reversed(rule_names):
            # The Arabic concept is enough for review detection; long
            # parenthetical example lists needlessly exhaust the input limit.
            name = re.sub(r"\([^()]*\)", "", name)
            name = re.sub(r"\s+", " ", name).strip()[:110]
            if not name or name in selected_names:
                continue
            if used_characters + len(name) + 2 > context_budget:
                continue
            selected_names.append(name)
            used_characters += len(name) + 2
        selected_names.reverse()
        review_context = context_prefix + "، ".join(selected_names) if selected_names else ""
    else:
        review_context = ""

    prompt_text = CHUNK_PROMPT_TEMPLATE.format(
        boundary_context=boundary_context,
        review_context=review_context,
    )
    return ("قسم من الدرس", prompt_text, "combined")


def build_recap_prompt(boundary_context: str) -> tuple[str, str, str]:
    """Return the single end-of-lecture recap-and-homework prompt."""
    return (
        "الخلاصة والواجب",
        RECAP_PROMPT_TEMPLATE.format(boundary_context=boundary_context),
        "summary",
    )


_CHUNK_SECTION_TAGS = (
    ("letters", "letters_section"),
    ("rules", "rules_section"),
    ("dialogues", "dialogues_section"),
    ("vocabulary", "vocabulary_section"),
)


def split_chunk_response(text: str) -> dict[str, str]:
    """Split one combined chunk response into its four bucket texts.

    Missing or malformed section tags simply resolve to an empty string for
    that bucket instead of raising, since a partial/garbled response should
    not lose the buckets that were extracted correctly.
    """
    result = {key: "" for key, _tag in _CHUNK_SECTION_TAGS}
    for key, tag in _CHUNK_SECTION_TAGS:
        match = re.search(
            rf"<{tag}>\s*(.*?)\s*</{tag}>",
            text or "",
            flags=re.IGNORECASE | re.DOTALL,
        )
        if match:
            result[key] = match.group(1).strip()
    return result


def missing_chunk_sections(text: str) -> list[str]:
    """Return the tag names a combined chunk response dropped, if any.

    A section that legitimately found nothing new still keeps its tag (e.g.
    <letters_section>لا يوجد حرف جديد في هذا الجزء.</letters_section>); this
    only flags a response that dropped an entire section's opening/closing
    tag, which would otherwise silently save that bucket as empty.
    """
    text = text or ""
    return [
        tag
        for _key, tag in _CHUNK_SECTION_TAGS
        if not re.search(
            rf"<{tag}>\s*.*?</{tag}>",
            text,
            flags=re.IGNORECASE | re.DOTALL,
        )
    ]


def chunk_response_has_all_sections(text: str) -> bool:
    """Return True only when all four section tags are present in the response."""
    return not missing_chunk_sections(text)


# Kept for PromptProfile compatibility. Russian prompt generation uses
# build_chunk_prompt/build_recap_prompt instead of this generic template.
SECTION_PROMPT_TEMPLATE = CHUNK_PROMPT_TEMPLATE
