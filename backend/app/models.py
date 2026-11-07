from typing import Literal

from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel

IncomeRange = Literal["under-30k", "30k-60k", "60k-100k", "over-100k"]
Area = Literal["income", "business", "investments", "realEstate"]
Risk = Literal["low", "moderate", "high", "notApplicable"]


class APIModel(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, extra="forbid")


class ProfileInput(APIModel):
    name: str = Field(default="Demo user", min_length=1, max_length=80, pattern=r"\S")
    occupation: str = Field(min_length=1, max_length=100, pattern=r"\S")
    income_range: IncomeRange
    business_owner: bool = Field(strict=True)
    investor: bool = Field(strict=True)
    property_owner: bool = Field(strict=True)


class Profile(ProfileInput):
    id: int
    created_at: str


class EconomicEvent(APIModel):
    id: int
    title: str
    category: str
    description: str


class AnalyzeInput(APIModel):
    user_id: int = Field(gt=0, strict=True)
    event_id: int = Field(gt=0, strict=True)


class Impact(APIModel):
    area: Area
    risk: Risk
    summary: str
    explanation: str
    considerations: list[str]
    rule_id: str | None


class Analysis(APIModel):
    id: int
    profile: Profile
    event: EconomicEvent
    impacts: list[Impact]
    assumptions: list[str]
    created_at: str


class ChatInput(APIModel):
    analysis_id: int = Field(gt=0, strict=True)
    question: str = Field(min_length=1, max_length=1000, pattern=r"\S")


class ChatOutput(APIModel):
    answer: str
    source: Literal["ai"] = "ai"


class Health(APIModel):
    status: Literal["ok"] = "ok"
    ai_configured: bool
