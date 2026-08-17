from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1 import router as v1_router
from app.core.config import get_settings

settings = get_settings()

app = FastAPI(
    title=settings.app_name,
    description=(
        "AI 투자교육·모의투자·투자일지 코칭 앱 API. "
        "모든 금액은 가상자금이며 실제 증권 주문을 접수하지 않는다."
    ),
    version="0.1.0",
)

# apps/web(Next.js) 로컬 개발 서버에서의 호출을 허용한다.
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/healthz", tags=["ops"])
def healthz():
    return {"status": "ok", "environment": settings.environment}


app.include_router(v1_router, prefix=settings.api_v1_prefix)
