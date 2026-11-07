import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException

from .advisor import AISettings, AdvisorError, explain
from .database import Database
from .models import Analysis, AnalyzeInput, ChatInput, ChatOutput, EconomicEvent, Health, Profile, ProfileInput


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

    @app.get("/api/health", response_model=Health)
    def health():
        return Health(aiConfigured=bool(settings.api_key))

    @app.get("/api/events", response_model=list[EconomicEvent])
    def events():
        return database.events()

    @app.post("/api/profile", response_model=Profile, status_code=201)
    def create_profile(data: ProfileInput):
        return database.create_profile(data)

    @app.post("/api/analyze", response_model=Analysis, status_code=201)
    def create_analysis(data: AnalyzeInput):
        try:
            return database.create_analysis(data.user_id, data.event_id)
        except LookupError as error:
            raise HTTPException(status_code=404, detail=str(error)) from None

    @app.get("/api/analysis/{analysis_id}", response_model=Analysis)
    def get_analysis(analysis_id: int):
        result = database.analysis(analysis_id)
        if result is None:
            raise HTTPException(status_code=404, detail="Analysis not found")
        return result

    @app.post("/api/chat", response_model=ChatOutput)
    async def chat(data: ChatInput):
        result = database.analysis(data.analysis_id)
        if result is None:
            raise HTTPException(status_code=404, detail="Analysis not found")
        try:
            answer = await explain(settings, result, data.question)
        except AdvisorError as error:
            raise HTTPException(status_code=error.status_code, detail=error.detail) from None
        return ChatOutput(answer=answer)

    return app


app = create_app()
