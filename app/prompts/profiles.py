"""Select the prompt family used for one extraction job."""

from collections.abc import Callable
from dataclasses import dataclass
from typing import Literal, cast

from app.prompts import (
    arabic_lecture_templates,
    english_course_templates,
    russian_course_templates,
)


ContentType = Literal["arabic", "english", "russian"]
DEFAULT_CONTENT_TYPE: ContentType = "arabic"
VALID_CONTENT_TYPES = frozenset({"arabic", "english", "russian"})


@dataclass(frozen=True)
class PromptProfile:
    build_outline_prompt: Callable[[str, str | None], str]
    build_boundary_context: Callable[[str | None, str | None], str]
    section_prompt_template: str
    end_question_prompt_template: str
    first_section_instruction: str = ""
    conclusion_instruction: str = ""


PROMPT_PROFILES: dict[ContentType, PromptProfile] = {
    "arabic": PromptProfile(
        build_outline_prompt=arabic_lecture_templates.build_outline_prompt,
        build_boundary_context=arabic_lecture_templates.build_boundary_context,
        section_prompt_template=(
            arabic_lecture_templates.SECTION_PROMPT_TEMPLATE
        ),
        end_question_prompt_template=(
            arabic_lecture_templates.END_QUESTION_PROMPT_TEMPLATE
        ),
        first_section_instruction=(
            arabic_lecture_templates.FIRST_SECTION_INTRO_INSTRUCTION
        ),
        conclusion_instruction=(
            arabic_lecture_templates.CONCLUSION_INSTRUCTION
        ),
    ),
    "english": PromptProfile(
        build_outline_prompt=english_course_templates.build_outline_prompt,
        build_boundary_context=english_course_templates.build_boundary_context,
        section_prompt_template=english_course_templates.SECTION_PROMPT_TEMPLATE,
        end_question_prompt_template=(
            english_course_templates.END_QUESTION_PROMPT_TEMPLATE
        ),
    ),
    "russian": PromptProfile(
        build_outline_prompt=russian_course_templates.build_outline_prompt,
        build_boundary_context=russian_course_templates.build_boundary_context,
        section_prompt_template=russian_course_templates.SECTION_PROMPT_TEMPLATE,
        end_question_prompt_template=(
            russian_course_templates.END_QUESTION_PROMPT_TEMPLATE
        ),
    ),
}


def validate_content_type(value: str | None) -> ContentType:
    """Return a supported content type or raise a user-facing error."""
    normalized = (value or DEFAULT_CONTENT_TYPE).strip().casefold()
    if normalized not in VALID_CONTENT_TYPES:
        raise ValueError(
            "نوع المحتوى يجب أن يكون 'arabic' أو 'english' أو 'russian'."
        )
    return cast(ContentType, normalized)


def get_prompt_profile(
    content_type: str = DEFAULT_CONTENT_TYPE,
) -> PromptProfile:
    return PROMPT_PROFILES[validate_content_type(content_type)]
