from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel, ConfigDict, Field

from loomi_api.api.dependencies import CsrfOwnerContext, DbSession
from loomi_api.db.models import UserFeedback

router = APIRouter(prefix="/api/v1/feedback", tags=["feedback"])


class FeedbackRequest(BaseModel):
    target_type: str = Field(min_length=1, max_length=80)
    target_id: str = Field(min_length=1, max_length=36)
    rating: int | None = Field(default=None, ge=-1, le=1)
    comment: str | None = Field(default=None, max_length=1000)


class FeedbackResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: str
    target_type: str
    target_id: str
    rating: int | None


@router.post("", response_model=FeedbackResponse, status_code=201)
async def create_feedback(
    payload: FeedbackRequest,
    session: DbSession,
    owner: CsrfOwnerContext,
) -> FeedbackResponse:
    feedback = UserFeedback(
        owner_user_id=owner.user.id,
        target_type=payload.target_type,
        target_id=payload.target_id,
        rating=payload.rating,
        comment=payload.comment,
    )
    session.add(feedback)
    await session.commit()
    await session.refresh(feedback)
    return FeedbackResponse(
        id=feedback.id,
        target_type=feedback.target_type,
        target_id=feedback.target_id,
        rating=feedback.rating,
    )
