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
حدود هذا الجزء داخل الدرس: ابدأ عند العبارة «{start_hint}» وانته عند العبارة «{end_hint}». التزم بما بينهما فقط، ولا تكرر الجزء السابق أو تنتقل إلى الجزء التالي."""


CHUNK_PROMPT_TEMPLATE = """استخرج من تسجيل درس اللغة الروسية المحدد أربعة أنواع من المحتوى معاً ضمن الجزء المحدد التالي من الدرس فقط.
{boundary_context}

قواعد عامة لكل الأقسام الأربعة: اعتمد قراءة المعلمة مرة واحدة، واحذف إعادة الطلاب. احذف الأسماء والمحاولات الفردية والمدح وأوامر الإعادة. احذف الحضور ومشكلات الاتصال والاستراحة والتنظيم والحديث الجانبي. التزم بحدود هذا الجزء فقط ولا تخترع محتوى من خارجها. لا تستخدم جداول Markdown ولا تكتب سؤال متابعة في أي قسم.

اكتب ردك بأربعة أقسام متتابعة بهذا الترتيب حرفياً، كل قسم كامل بين وسمه فقط، ولا تحذف وسم قسم حتى لو كان فارغاً:

<letters_section>
الحروف الجديدة فقط. تحت <subheading>الحروف الجديدة</subheading>، لكل حرف: الشكل الكبير والصغير معاً مثل <russian>А а</russian>، ثم <pronunciation>اسم الحرف وصوته داخل الكلمات</pronunciation>، ثم <translation>وظيفته أو أقرب وصف عربي لصوته</translation>. <highlight>ملاحظة نطق: ...</highlight> فقط لفرق صوتي مهم. لا تشرح خطوات رسم الحرف. بحد أقصى ستة مقاطع لكل ساكن أو مقارنتين لكل متحرك؛ احذف السلاسل الطويلة العشوائية. لا تنشئ قائمة مفردات هنا. إذا لم يظهر حرف جديد، اكتب فقط: لا يوجد حرف جديد في هذا الجزء.
</letters_section>

<rules_section>
القواعد وتطبيقاتها فقط. لكل قاعدة: <subheading>اسم القاعدة المختصر</subheading> ثم شرح عربي فصيح قصير يبيّن متى تُستخدم، ثم من مثالين إلى أربعة أمثلة جديدة فقط، كل مثال: <russian>النص الروسي</russian> <pronunciation>اللفظ</pronunciation> <translation>المعنى</translation>.

{review_context}

لا تنشئ قائمة مفردات هنا، ولا تكرر شرح القاعدة بسبب كثرة تطبيق الطلاب. إذا لم تظهر قاعدة جديدة، اكتب فقط: لا توجد قاعدة جديدة في هذا الجزء.
</rules_section>

<dialogues_section>
الحوارات التعليمية النموذجية فقط. ابدأ بـ <subheading>الحوارات الروسية</subheading>، ولكل حوار عنوان قصير ثم جمله الفريدة بترتيب المعلمة، بصيغة A وB فقط:
<speaker>A</speaker> <russian>الجملة الصحيحة</russian> <pronunciation>اللفظ</pronunciation> <translation>المعنى</translation>

لا تعامل المحادثة الصفية العشوائية كحوار تعليمي، ولا تنشئ قائمة مفردات هنا. إذا لم يظهر حوار تعليمي، اكتب فقط: لا يوجد حوار تعليمي في هذا الجزء.
</dialogues_section>

<vocabulary_section>
مفرداته وعباراته المفيدة فقط: كلمات الدرس، ما تشرحه المعلمة أو تقرؤه كنموذج، تحياتها ووداعها وتعليماتها الصفية القابلة لإعادة الاستخدام، وعبارات ومفردات الحوارات. لكل مدخل:
<vocabulary_item><category>تصنيف موضوعي قصير</category><russian>الكلمة الصحيحة</russian><pronunciation>أقرب لفظ</pronunciation><translation>المعنى بالعربية</translation><english>المعنى بالإنجليزية</english></vocabulary_item>

لا تضف حروفاً منفردة أو مقاطع بلا معنى، ولا تكرر المدخل بسبب إعادة الطلاب. لا ترتب أبجدياً. إذا لم تظهر مفردة جديدة، لا تكتب أي كتلة <vocabulary_item>.
</vocabulary_section>
"""


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
        start_hint=start_hint or "غير محددة",
        end_hint=end_hint or "غير محددة",
    )


def build_chunk_prompt(
    boundary_context: str,
    prior_rule_names: Iterable[str] = (),
) -> tuple[str, str, str]:
    """Return the single combined prompt covering all four buckets for one chunk."""
    rule_names = [name.strip() for name in prior_rule_names if name.strip()]
    if rule_names:
        review_context = (
            "قواعد سبق تلخيصها في محاضرات سابقة: "
            + "، ".join(rule_names)
            + ". إذا أعادت المعلمة واحدة منها، اكتب تحت اسمها سطرًا يبدأ بـ "
            "\"مراجعة:\" ثم أضف المثال أو التفصيل الجديد فقط، من دون إعادة الشرح الكامل."
        )
    else:
        review_context = (
            "هذه أول محاضرة في النسخة التراكمية؛ اشرح كل قاعدة جديدة مرة واحدة فقط."
        )

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


# Kept for PromptProfile compatibility. Russian prompt generation uses
# build_chunk_prompt/build_recap_prompt instead of this generic template.
SECTION_PROMPT_TEMPLATE = CHUNK_PROMPT_TEMPLATE
