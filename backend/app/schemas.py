from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator
from pydantic.alias_generators import to_camel

IncomeRange = Literal["under-30k", "30k-60k", "60k-100k", "over-100k"]
StoredIncomeRange = IncomeRange | Literal["75k-100k", "100k-125k"]
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


class PropertyHolding(APIModel):
    property_type: str = Field(min_length=1, max_length=50, pattern=r"\S")
    property_count: int = Field(default=1, ge=1, strict=True)


class ProfileData(ProfileInput):
    income_range: StoredIncomeRange
    stocks: list[str] = Field(default_factory=list)
    properties: list[PropertyHolding] = Field(default_factory=list)


class Profile(ProfileData):
    id: int
    created_at: str


class ProfileUpdate(APIModel):
    name: str | None = Field(default=None, min_length=1, max_length=80, pattern=r"\S")
    occupation: str | None = Field(default=None, min_length=1, max_length=100, pattern=r"\S")
    income_range: IncomeRange | None = None
    business_owner: bool | None = Field(default=None, strict=True)
    investor: bool | None = Field(default=None, strict=True)
    property_owner: bool | None = Field(default=None, strict=True)

    @model_validator(mode="after")
    def validate_changes(self):
        if not self.model_fields_set:
            raise ValueError("Provide at least one profile field to update")
        if any(getattr(self, field) is None for field in self.model_fields_set):
            raise ValueError("Profile fields cannot be null")
        return self


class ProfileChanges(ProfileUpdate):
    income_range: StoredIncomeRange | None = None
    stocks: list[str] | None = None
    properties: list[PropertyHolding] | None = None


class EconomicEvent(APIModel):
    id: int
    title: str
    category: str
    description: str


class AnalyzeInput(APIModel):
    user_id: int = Field(gt=0, strict=True)
    event_id: int = Field(gt=0, strict=True)


class AnalyzeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    user_id: int = Field(gt=0, strict=True)
    event_id: int = Field(gt=0, strict=True)


class RiskSummary(BaseModel):
    income_risk: str
    business_risk: str
    investment_risk: str
    real_estate_risk: str


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
    overall_summary: str | None = None
    recommendations: list[str] = Field(default_factory=list)
    recommendation_source: Literal["rules"] = "rules"


class AnalysisHistoryItem(APIModel):
    analysis_id: int
    event: str
    created_at: str


class Dashboard(APIModel):
    profile: Profile
    event: EconomicEvent
    analysis: Analysis
    recommendations: list[str]


class ChatMessage(APIModel):
    id: int
    user_id: int
    analysis_id: int
    role: Literal["user", "assistant"]
    message: str
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
