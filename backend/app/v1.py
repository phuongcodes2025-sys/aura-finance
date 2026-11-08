from fastapi import APIRouter, Path

from .advisor import AISettings
from .database import Database, RecordNotFoundError
from .routes import chat_reply, database_errors, saved_analysis
from . import v1_schemas as schemas


def create_router(database: Database, settings: AISettings) -> APIRouter:
    router = APIRouter(prefix="/api/v1", tags=["Version 1"])

    @router.post("/profile", response_model=schemas.ProfileCreated, status_code=201)
    def create_profile(data: schemas.ProfileCreate):
        profile = database.create_profile(data.profile_data())
        return schemas.ProfileCreated(id=profile.id)

    @router.get("/profile/{user_id}", response_model=schemas.ProfileResponse)
    def get_profile(user_id: int = Path(gt=0)):
        with database_errors():
            profile = database.profile(user_id)
            if profile is None:
                raise RecordNotFoundError("Profile not found")
        return schemas.ProfileResponse.from_profile(profile)

    @router.patch("/profile/{user_id}", response_model=schemas.ProfileResponse)
    def update_profile(data: schemas.ProfileUpdate, user_id: int = Path(gt=0)):
        with database_errors():
            profile = database.update_profile(user_id, data.profile_changes())
        return schemas.ProfileResponse.from_profile(profile)

    @router.put("/profile/{user_id}", response_model=schemas.MessageResponse)
    def replace_profile(data: schemas.ProfileCreate, user_id: int = Path(gt=0)):
        changes = schemas.ProfileUpdate.model_validate(data.model_dump())
        with database_errors():
            database.update_profile(user_id, changes.profile_changes())
        return schemas.MessageResponse(message="Profile updated")

    @router.delete("/profile/{user_id}", response_model=schemas.MessageResponse)
    def delete_profile(user_id: int = Path(gt=0)):
        with database_errors():
            database.delete_profile(user_id)
        return schemas.MessageResponse(message="Profile deleted")

    @router.get("/profile/{user_id}/analyses", response_model=list[schemas.AnalysisHistoryItem])
    def analysis_history(user_id: int = Path(gt=0)):
        with database_errors():
            history = database.analysis_history(user_id)
        return [schemas.AnalysisHistoryItem.model_validate(item.model_dump()) for item in history]

    @router.get("/events", response_model=list[schemas.EventResponse])
    def events():
        return [
            schemas.EventResponse(id=event.id, event_name=event.title,
                                  category=event.category, summary=event.description)
            for event in database.events()
        ]

    @router.get("/events/{event_id}", response_model=schemas.EventResponse)
    def event_details(event_id: int = Path(gt=0)):
        with database_errors():
            event = database.event(event_id)
            if event is None:
                raise RecordNotFoundError("Economic event not found")
        return schemas.EventResponse(id=event.id, event_name=event.title,
                                     category=event.category, summary=event.description)

    @router.post("/analyze", response_model=schemas.AnalysisResponse, status_code=201)
    def analyze(data: schemas.AnalyzeInput):
        with database_errors():
            result = database.create_analysis(data.user_id, data.event_id)
        return schemas.AnalysisResponse.from_analysis(result)

    @router.get("/analyze/{analysis_id}", response_model=schemas.AnalysisResponse)
    def get_analysis(analysis_id: int = Path(gt=0)):
        return schemas.AnalysisResponse.from_analysis(saved_analysis(database, analysis_id))

    @router.get("/dashboard/{analysis_id}", response_model=schemas.DashboardResponse)
    def dashboard(analysis_id: int = Path(gt=0)):
        result = saved_analysis(database, analysis_id)
        return schemas.DashboardResponse(
            profile=schemas.ProfileResponse.from_profile(result.profile),
            event=schemas.EventResponse(id=result.event.id, event_name=result.event.title,
                                       category=result.event.category, summary=result.event.description),
            analysis=schemas.AnalysisResponse.from_analysis(result),
            recommendations=result.recommendations,
        )

    @router.post("/chat", response_model=schemas.ChatResponse)
    async def chat(data: schemas.ChatInput):
        answer = await chat_reply(database, settings, data.analysis_id, data.message, data.user_id)
        return schemas.ChatResponse(response=answer)

    @router.get("/chat/{analysis_id}", response_model=list[schemas.ChatMessage])
    def chat_history(analysis_id: int = Path(gt=0)):
        with database_errors():
            history = database.chat_history(analysis_id)
        return [schemas.ChatMessage.model_validate(item.model_dump()) for item in history]

    return router
