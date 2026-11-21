import re

from app.models.schemas import ExtractionItem, PromptItem
from app.prompts.profiles import (
    DEFAULT_CONTENT_TYPE,
    ContentType,
    get_prompt_profile,
)
from app.prompts import english_course_templates, russian_course_templates
from app.utils.arabic import number_main_heading


class PromptGenerator:
    _SOURCE_NUMBER_PREFIX = re.compile(
        r"^\s*(?:(?:section|topic|chapter|module)\s*)?"
        r"(?P<number>\d+)(?:[.)\-:]|\s|$)",
        flags=re.IGNORECASE,
    )

    @classmethod
    def generate_prompts(
        cls,
        items: list[ExtractionItem],
        content_type: ContentType = DEFAULT_CONTENT_TYPE,
        prior_rule_names: list[str] | None = None,
    ) -> list[PromptItem]:
        if content_type == "russian":
            chunks = [item for item in items if item.kind == "main"]
            prompts: list[PromptItem] = []
            for chunk in chunks:
                boundary_context = russian_course_templates.build_boundary_context(
                    chunk.start_hint,
                    chunk.end_hint,
                )
                heading, prompt_text, output_kind = (
                    russian_course_templates.build_chunk_prompt(
                        boundary_context,
                        prior_rule_names or (),
                    )
                )
                prompts.append(
                    PromptItem(
                        heading=heading,
                        prompt_text=prompt_text,
                        output_kind=output_kind,
                    )
                )

            last_boundary = (
                russian_course_templates.build_boundary_context(
                    chunks[-1].start_hint,
                    chunks[-1].end_hint,
                )
                if chunks
                else ""
            )
            recap_heading, recap_prompt_text, recap_kind = (
                russian_course_templates.build_recap_prompt(last_boundary)
            )
            prompts.append(
                PromptItem(
                    heading=recap_heading,
                    prompt_text=recap_prompt_text,
                    output_kind=recap_kind,
                )
            )
            return prompts

        if content_type == "english":
            return cls._generate_english_prompts(items)

        profile = get_prompt_profile(content_type)
        prompts: list[PromptItem] = []
        main_heading_number = 0
        for item in items:
            if item.kind == "end_question":
                prompt_text = profile.end_question_prompt_template.format(
                    question_title=item.title
                )
                prompts.append(
                    PromptItem(
                        heading=f"سؤال: {item.title}",
                        prompt_text=prompt_text,
                    )
                )
                continue

            if item.kind != "main" or item.level != 1:
                continue

            main_heading_number += 1
            numbered_title = number_main_heading(
                item.title,
                main_heading_number,
            )
            prompt_text = profile.section_prompt_template.format(
                heading_title=numbered_title,
                boundary_context=profile.build_boundary_context(
                    item.start_hint,
                    item.end_hint,
                ),
            )

            if main_heading_number == 1 and profile.first_section_instruction:
                prompt_text += profile.first_section_instruction

            if (
                profile.conclusion_instruction
                and ("خاتم" in numbered_title or "نهاي" in numbered_title)
            ):
                prompt_text += profile.conclusion_instruction

            prompts.append(
                PromptItem(
                    heading=numbered_title,
                    prompt_text=prompt_text,
                )
            )
        return prompts

    @classmethod
    def _generate_english_prompts(
        cls,
        items: list[ExtractionItem],
    ) -> list[PromptItem]:
        """Keep English topic notes, recap, and review questions in study order."""
        profile = get_prompt_profile("english")
        topic_prompts: list[PromptItem] = []
        question_items: list[ExtractionItem] = []

        for item in items:
            if item.kind == "end_question":
                question_items.append(item)
                continue
            if item.kind != "main" or item.level != 1:
                continue

            source_title = item.title
            topic_prompts.append(
                PromptItem(
                    heading=source_title,
                    prompt_text=profile.section_prompt_template.format(
                        heading_title=source_title,
                        boundary_context=profile.build_boundary_context(
                            item.start_hint,
                            item.end_hint,
                        ),
                    ),
                )
            )

        numbered_topics = [
            (cls._SOURCE_NUMBER_PREFIX.match(prompt.heading), prompt)
            for prompt in topic_prompts
        ]
        source_numbers = [
            int(match.group("number"))
            for match, _ in numbered_topics
            if match is not None
        ]
        if (
            len(source_numbers) == len(topic_prompts)
            and len(set(source_numbers)) == len(source_numbers)
        ):
            topic_prompts = [
                prompt
                for _, prompt in sorted(
                    numbered_topics,
                    key=lambda entry: int(entry[0].group("number")),
                )
            ]

        prompts = topic_prompts
        prompts.append(
            PromptItem(
                heading="خلاصة المحاضرة",
                prompt_text=english_course_templates.RECAP_PROMPT_TEMPLATE,
            )
        )
        for item in question_items:
            prompts.append(
                PromptItem(
                    heading=f"سؤال للمراجعة: {item.title}",
                    prompt_text=profile.end_question_prompt_template.format(
                        question_title=item.title,
                    ),
                )
            )
        prompts.append(
            PromptItem(
                heading="استخراج المعلومات التنظيمية",
                prompt_text=english_course_templates.LOGISTICS_PROMPT_TEMPLATE,
                output_kind="logistics",
            )
        )
        return prompts
