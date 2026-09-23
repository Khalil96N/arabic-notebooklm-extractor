from typing import Literal

from pydantic import BaseModel


class ExtractionItem(BaseModel):
    title: str
    level: int
    kind: Literal["main", "end_question"] = "main"
    start_hint: str | None = None
    end_hint: str | None = None


class ExtractionPlan(BaseModel):
    discovery_text: str
    items: list[ExtractionItem]


class PromptItem(BaseModel):
    heading: str
    prompt_text: str
    output_kind: Literal["summary", "vocabulary", "combined"] = "summary"
