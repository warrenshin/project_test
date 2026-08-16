from fastapi import APIRouter

from app.api.v1 import ai, auth, instruments, journals, learning, portfolios

router = APIRouter()
router.include_router(auth.router, prefix="/auth", tags=["auth"])
router.include_router(learning.router, tags=["learning"])
router.include_router(instruments.router, tags=["instruments"])
router.include_router(portfolios.router, tags=["portfolios"])
router.include_router(journals.router, tags=["journals"])
router.include_router(ai.router, prefix="/ai", tags=["ai"])
