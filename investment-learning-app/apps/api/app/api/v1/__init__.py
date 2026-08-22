from fastapi import APIRouter

from app.api.v1 import ai, auth, challenges, instruments, journals, learning, notifications, portfolios

router = APIRouter()
router.include_router(auth.router, prefix="/auth", tags=["auth"])
router.include_router(learning.router, tags=["learning"])
router.include_router(instruments.router, tags=["instruments"])
router.include_router(portfolios.router, tags=["portfolios"])
router.include_router(journals.router, tags=["journals"])
router.include_router(ai.router, prefix="/ai", tags=["ai"])
router.include_router(challenges.router, tags=["challenges"])
router.include_router(notifications.router, tags=["notifications"])
