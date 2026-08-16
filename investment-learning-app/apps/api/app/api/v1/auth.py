"""계정·인증·동의. 명세서 6.1, 9.2 참고.

Phase 1에서 구현 예정: JWT + refresh-token 회전, Apple/Google/이메일 로그인,
약관 버전·동의시각 감사로그.
"""

from fastapi import APIRouter, HTTPException, status

router = APIRouter()

_NOT_IMPLEMENTED = "Phase 1에서 구현 예정 (docs/product-spec.md 6.1, 9.2)"


@router.post("/signup", status_code=status.HTTP_501_NOT_IMPLEMENTED)
def signup():
    raise HTTPException(status_code=501, detail=_NOT_IMPLEMENTED)


@router.post("/login", status_code=status.HTTP_501_NOT_IMPLEMENTED)
def login():
    raise HTTPException(status_code=501, detail=_NOT_IMPLEMENTED)


@router.post("/refresh", status_code=status.HTTP_501_NOT_IMPLEMENTED)
def refresh():
    raise HTTPException(status_code=501, detail=_NOT_IMPLEMENTED)
