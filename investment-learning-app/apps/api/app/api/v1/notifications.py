"""인앱 알림(스텁) API. 실제 푸시 발송은 없다 — 조회 시점에 서버가 계산한
"지금 보여줄 알림" 목록만 돌려준다. app/domain/services/notifications.py 참고."""

from pydantic import BaseModel
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session as DbSession

from app.core.db import get_db
from app.core.deps import get_current_user
from app.domain.services import notifications as notifications_service
from app.domain.user import User

router = APIRouter()


class NotificationResponse(BaseModel):
    type: str
    title: str
    body: str
    href: str


@router.get("/me/notifications", response_model=list[NotificationResponse])
def list_my_notifications(db: DbSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    items = notifications_service.get_notifications(db, current_user.id)
    return [NotificationResponse(type=i.type, title=i.title, body=i.body, href=i.href) for i in items]
