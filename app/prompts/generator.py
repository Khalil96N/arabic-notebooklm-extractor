from app.models.schemas import ExtractionItem, PromptItem
from app.prompts.templates import (
    CONCLUSION_INSTRUCTION,
    END_QUESTION_PROMPT_TEMPLATE,
    SECTION_PROMPT_TEMPLATE,
)
from app.utils.arabic import number_main_heading


class PromptGenerator:
    PROMPT_TEMPLATE = SECTION_PROMPT_TEMPLATE
    END_QUESTION_PROMPT_TEMPLATE = END_QUESTION_PROMPT_TEMPLATE

    @classmethod
    def generate_prompts(
        cls,
        items: list[ExtractionItem],
    ) -> list[PromptItem]:
        prompts: list[PromptItem] = []
        main_heading_number = 0

        for item in items:
            if item.kind == "end_question":
                prompt_text = cls.END_QUESTION_PROMPT_TEMPLATE.format(
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
            prompt_text = cls.PROMPT_TEMPLATE.format(
                heading_title=numbered_title
            )

            if "خاتم" in numbered_title or "نهاي" in numbered_title:
                prompt_text += CONCLUSION_INSTRUCTION

            prompts.append(
                PromptItem(
                    heading=numbered_title,
                    prompt_text=prompt_text,
                )
            )
        return prompts
