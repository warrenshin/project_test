from datetime import date
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field, field_validator

ConsentType = Literal["TERMS", "PRIVACY", "MARKETING"]

MIN_SIGNUP_AGE_YEARS = 14


class ConsentInput(BaseModel):
    consent_type: ConsentType
    version: str
    agreed: bool


class SignupRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    birth_date: date
    consents: list[ConsentInput]

    @field_validator("consents")
    @classmethod
    def require_mandatory_consents(cls, consents: list[ConsentInput]) -> list[ConsentInput]:
        agreed_types = {c.consent_type for c in consents if c.agreed}
        missing = {"TERMS", "PRIVACY"} - agreed_types
        if missing:
            raise ValueError(f"필수 동의 항목이 누락되었습니다: {sorted(missing)}")
        return consents


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class RefreshRequest(BaseModel):
    refresh_token: str


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class UserResponse(BaseModel):
    id: UUID
    email: EmailStr
