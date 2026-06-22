from typing import Literal

from pydantic import BaseModel


class ExtractionItem(BaseModel):
    title: str
    level: int
    kind: Literal["main", "end_question"] = "main"


class ExtractionPlan(BaseModel):
    discovery_text: str
    items: list[ExtractionItem]


class PromptItem(BaseModel):
    heading: str
    prompt_text: str
