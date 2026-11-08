from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from pydantic.alias_generators import to_camel

from .schemas import Analysis, Profile, ProfileChanges, ProfileData, PropertyHolding, StoredIncomeRange

Ticker = Annotated[str, Field(min_length=1, max_length=10, pattern=r"^[A-Za-z0-9][A-Za-z0-9.-]*$")]


class V1Model(BaseModel):
    model_config = ConfigDict(extra="forbid")


class PropertyInput(V1Model):
    property_type: str = Field(min_length=1, max_length=50, pattern=r"\S")
    property_count: int = Field(default=1, ge=1, strict=True)

    @field_validator("property_type")
    @classmethod
    def trim_type(cls, value: str) -> str:
        return value.strip()


class ProfileCreate(V1Model):
    name: str = Field(min_length=1, max_length=80, pattern=r"\S")
    occupation: str = Field(min_length=1, max_length=100, pattern=r"\S")
    income_range: StoredIncomeRange
    business_owner: bool = Field(default=False, strict=True)
    stocks: list[Ticker] = Field(default_factory=list, max_length=100)
    properties: list[PropertyInput] = Field(default_factory=list, max_length=100)

    @field_validator("stocks")
    @classmethod
    def normalize_stocks(cls, values: list[str]) -> list[str]:
        normalized = [value.upper() for value in values]
        if len(normalized) != len(set(normalized)):
            raise ValueError("Stock tickers must be unique")
        return normalized

    def profile_data(self) -> ProfileData:
        return ProfileData(
            name=self.name, occupation=self.occupation, incomeRange=self.income_range,
            businessOwner=self.business_owner, investor=bool(self.stocks),
            propertyOwner=bool(self.properties), stocks=self.stocks,
            properties=[
                PropertyHolding(propertyType=item.property_type, propertyCount=item.property_count)
                for item in self.properties
            ],
        )


class ProfileUpdate(V1Model):
    name: str | None = Field(default=None, min_length=1, max_length=80, pattern=r"\S")
    occupation: str | None = Field(default=None, min_length=1, max_length=100, pattern=r"\S")
    income_range: StoredIncomeRange | None = None
    business_owner: bool | None = Field(default=None, strict=True)
    stocks: list[Ticker] | None = Field(default=None, max_length=100)
    properties: list[PropertyInput] | None = Field(default=None, max_length=100)

    @field_validator("stocks")
    @classmethod
    def normalize_stocks(cls, values: list[str] | None) -> list[str] | None:
        return ProfileCreate.normalize_stocks(values) if values is not None else None

    @model_validator(mode="after")
    def validate_changes(self):
        if not self.model_fields_set:
            raise ValueError("Provide at least one profile field to update")
        if any(getattr(self, field) is None for field in self.model_fields_set):
            raise ValueError("Profile fields cannot be null")
        return self

    def profile_changes(self) -> ProfileChanges:
        changes = {
            to_camel(key): value for key, value in self.model_dump(exclude_unset=True).items()
        }
        if self.properties is not None:
            changes["properties"] = [
                {"propertyType": item.property_type, "propertyCount": item.property_count}
                for item in self.properties
            ]
        return ProfileChanges.model_validate(changes)


class ProfileResponse(V1Model):
    id: int
    name: str
    occupation: str
    income_range: StoredIncomeRange
    business_owner: bool
    investor: bool
    property_owner: bool
    stocks: list[str]
    properties: list[PropertyInput]
    created_at: str

    @classmethod
    def from_profile(cls, profile: Profile):
        return cls.model_validate(profile.model_dump())


class ProfileCreated(V1Model):
    id: int
    message: Literal["Profile created successfully"] = "Profile created successfully"


class MessageResponse(V1Model):
    message: str


class EventResponse(V1Model):
    id: int
    event_name: str
    category: str
    summary: str


class AnalyzeInput(V1Model):
    user_id: int = Field(gt=0, strict=True)
    event_id: int = Field(gt=0, strict=True)


class ImpactResponse(V1Model):
    risk: Literal["Low", "Moderate", "High", "Not applicable"]
    explanation: str
    summary: str


class AnalysisResponse(V1Model):
    analysis_id: int
    created_at: str
    income: ImpactResponse
    business: ImpactResponse
    investments: ImpactResponse
    real_estate: ImpactResponse
    overall_summary: str
    recommendations: list[str]
    recommendation_source: Literal["rules"] = "rules"
    assumptions: list[str]

    @classmethod
    def from_analysis(cls, analysis: Analysis):
        risks = {
            "low": "Low", "moderate": "Moderate", "high": "High",
            "notApplicable": "Not applicable",
        }
        areas = {"realEstate": "real_estate"}
        impacts = {
            areas.get(impact.area, impact.area): {
                "risk": risks[impact.risk],
                "explanation": impact.explanation,
                "summary": impact.summary,
            }
            for impact in analysis.impacts
        }
        return cls.model_validate({
            "analysis_id": analysis.id, "created_at": analysis.created_at,
            **impacts, "overall_summary": analysis.overall_summary,
            "recommendations": analysis.recommendations,
            "recommendation_source": analysis.recommendation_source,
            "assumptions": analysis.assumptions,
        })


class AnalysisHistoryItem(V1Model):
    analysis_id: int
    event: str
    created_at: str


class ChatInput(V1Model):
    user_id: int = Field(gt=0, strict=True)
    analysis_id: int = Field(gt=0, strict=True)
    message: str = Field(min_length=1, max_length=1000, pattern=r"\S")


class ChatResponse(V1Model):
    response: str
    source: Literal["ai"] = "ai"


class ChatMessage(V1Model):
    id: int
    user_id: int
    analysis_id: int
    role: Literal["user", "assistant"]
    message: str
    created_at: str


class DashboardResponse(V1Model):
    profile: ProfileResponse
    event: EventResponse
    analysis: AnalysisResponse
    recommendations: list[str]
