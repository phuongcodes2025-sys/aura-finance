from contextlib import contextmanager

from fastapi import HTTPException

from .advisor import AISettings, AdvisorError, explain
from .database import Database, ProfileConflictError, RecordNotFoundError
from .schemas import Analysis


@contextmanager
def database_errors():
    try:
        yield
    except RecordNotFoundError as error:
        raise HTTPException(status_code=404, detail=str(error)) from None
    except ProfileConflictError as error:
        raise HTTPException(status_code=409, detail=str(error)) from None


def saved_analysis(database: Database, analysis_id: int) -> Analysis:
    result = database.analysis(analysis_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Analysis not found")
    return result


async def chat_reply(
    database: Database, settings: AISettings, analysis_id: int,
    question: str, user_id: int | None = None,
) -> str:
    result = saved_analysis(database, analysis_id)
    if user_id is not None and result.profile.id != user_id:
        raise HTTPException(status_code=404, detail="Analysis not found for this profile")
    try:
        answer = await explain(settings, result, question)
    except AdvisorError as error:
        raise HTTPException(status_code=error.status_code, detail=error.detail) from None
    with database_errors():
        database.save_chat(analysis_id, result.profile.id, question, answer, result.created_at)
    return answer
