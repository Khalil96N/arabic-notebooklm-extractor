from app.models.schemas import ExtractionItem, PromptItem
from app.prompts.profiles import (
    DEFAULT_CONTENT_TYPE,
    ContentType,
    get_prompt_profile,
)
from app.prompts import russian_course_templates
from app.utils.arabic import number_main_heading


class PromptGenerator:
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
