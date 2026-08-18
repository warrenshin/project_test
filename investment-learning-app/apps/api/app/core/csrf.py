"""CSRF 방어: 상태 변경 요청(POST/PUT/PATCH/DELETE)에 대한 Origin 검증.

쿠키 기반 인증으로 전환하면 브라우저가 쿠키를 자동으로 실어 보내므로(폼 제출이든
fetch든) CORS만으로는 막을 수 없는 크로스사이트 요청 위조가 새로 생긴다. 이 미들웨어는
SameSite=Lax 쿠키 정책과 함께 2중 방어선을 이룬다(선택 이유는 PR 설명 참고):

- GET/HEAD/OPTIONS는 정의상 상태를 바꾸지 않으므로 검사하지 않는다
  (OPTIONS는 CORS preflight이기도 하다).
- 그 외 메서드는 Origin 헤더가 CORS 허용 목록에 있는 경우에만 통과시킨다.
- Origin이 없거나 허용 목록에 없으면 그 즉시 403으로 거부한다(요청을 라우터까지
  들여보내지 않는다) — "실패 시 닫힌다"는 정책을 명확히 한다. 최신 브라우저의
  fetch/XHR/form 제출은 크로스사이트 POST에 Origin 헤더를 항상 붙이므로, 이 헤더가
  없다는 것은 스크립트가 아닌 다른 경로(또는 헤더를 조작한 공격 도구)로 보낸 요청일
  가능성이 높다고 보고 안전한 쪽으로 거부한다.
"""

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

from app.core.config import get_settings

_SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}


class OriginCheckMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        if request.method in _SAFE_METHODS:
            return await call_next(request)

        settings = get_settings()
        origin = request.headers.get("origin")
        if origin is None or origin not in settings.cors_allowed_origins:
            return JSONResponse(status_code=403, content={"detail": "요청 출처를 확인할 수 없습니다."})

        return await call_next(request)
