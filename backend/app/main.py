import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Path

from .advisor import AISettings
from .database import Database
from .routes import chat_reply, database_errors, saved_analysis
from .schemas import (
    Analysis, AnalysisHistoryItem, AnalyzeInput, AnalyzeRequest, ChatInput, ChatMessage, ChatOutput,
    Dashboard, EconomicEvent, Health, Profile, RiskSummary, ProfileInput, ProfileUpdate,
)
from .v1 import create_router


def create_app(database_path: str | None = None, ai_settings: AISettings | None = None) -> FastAPI:
    database = Database(database_path or os.getenv("DATABASE_PATH", "./aura.sqlite3"))
    settings = ai_settings or AISettings(
        api_key=os.getenv("OPENAI_API_KEY", "").strip(),
        base_url=os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1"),
        model=os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
    )
    settings.validate()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        database.initialize()
        yield

    app = FastAPI(title="Aura Finance", version="0.1.0", lifespan=lifespan)

    @app.get("/")
    def read_root():
        return {"message": "Welcome to Aura Finance API", "docs": "/docs", "health": "/api/health"}

    @app.get("/api/health", response_model=Health)
    def health():
        return Health(aiConfigured=bool(settings.api_key))

    @app.get("/api/events", response_model=list[EconomicEvent])
    def events():
        return database.events()

    @app.get("/api/events/{event_id}", response_model=EconomicEvent)
    def event_details(event_id: int = Path(gt=0)):
        event = database.event(event_id)
        if event is None:
            raise HTTPException(status_code=404, detail="Economic event not found")
        return event

    @app.post("/api/profile", response_model=Profile, status_code=201)
    def create_profile(data: ProfileInput):
        return database.create_profile(data)

    @app.get("/api/profile/{user_id}", response_model=Profile)
    def get_profile(user_id: int = Path(gt=0)):
        result = database.profile(user_id)
        if result is None:
            raise HTTPException(status_code=404, detail="Profile not found")
        return result

    @app.patch("/api/profile/{user_id}", response_model=Profile)
    def update_profile(data: ProfileUpdate, user_id: int = Path(gt=0)):
        with database_errors():
            return database.update_profile(user_id, data)

    @app.delete("/api/profile/{user_id}")
    def delete_profile(user_id: int = Path(gt=0)):
        with database_errors():
            database.delete_profile(user_id)
        return {"message": "Profile deleted"}

    @app.get("/api/profile/{user_id}/analyses", response_model=list[AnalysisHistoryItem])
    def analysis_history(user_id: int = Path(gt=0)):
        with database_errors():
            return database.analysis_history(user_id)

    @app.post("/api/analyze", response_model=Analysis, status_code=201)
    def create_analysis(data: AnalyzeInput):
        with database_errors():
            return database.create_analysis(data.user_id, data.event_id)

    @app.post("/analyze", response_model=RiskSummary, tags=["Analyze"])
    def analyze_risks(data: AnalyzeRequest):
        with database_errors():
            result = database.create_analysis(data.user_id, data.event_id)
        labels = {"low": "Low", "moderate": "Moderate", "high": "High", "notApplicable": "Not applicable"}
        risks = {impact.area: labels[impact.risk] for impact in result.impacts}
        return RiskSummary(
            income_risk=risks["income"], business_risk=risks["business"],
            investment_risk=risks["investments"], real_estate_risk=risks["realEstate"],
        )

    @app.get("/api/analysis/{analysis_id}", response_model=Analysis)
    def get_analysis(analysis_id: int = Path(gt=0)):
        return saved_analysis(database, analysis_id)

    @app.get("/api/dashboard/{analysis_id}", response_model=Dashboard)
    def dashboard(analysis_id: int = Path(gt=0)):
        result = saved_analysis(database, analysis_id)
        return Dashboard(profile=result.profile, event=result.event,
                         analysis=result, recommendations=result.recommendations)

    @app.get("/api/chat/{analysis_id}", response_model=list[ChatMessage])
    def chat_history(analysis_id: int = Path(gt=0)):
        with database_errors():
            return database.chat_history(analysis_id)

    @app.post("/api/chat", response_model=ChatOutput)
    async def chat(data: ChatInput):
        answer = await chat_reply(database, settings, data.analysis_id, data.question)
        return ChatOutput(answer=answer)

    app.include_router(create_router(database, settings))
    return app


app = create_app()
