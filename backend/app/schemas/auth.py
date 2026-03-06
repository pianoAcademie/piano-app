from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class RegisterRequest(BaseModel):
    email: str = Field(min_length=3, max_length=255)
    password: str = Field(min_length=8, max_length=128)
    first_name: str | None = Field(default=None, min_length=1, max_length=100)
    last_name: str | None = Field(default=None, min_length=1, max_length=100)
    registration_subject_type: Literal["self", "child"] = "self"
    transactional_email_opt_in: bool = True
    transactional_sms_opt_in: bool = True
    marketing_email_opt_in: bool = False
    marketing_sms_opt_in: bool = False
    student_photo_filename: str | None = Field(default=None, min_length=1, max_length=255)
    student_photo_mime_type: str | None = Field(default=None, min_length=3, max_length=120)
    address_line: str | None = Field(default=None, min_length=1, max_length=255)
    phone: str | None = Field(default=None, min_length=3, max_length=30)
    residence_country: str = Field(default="FR", min_length=2, max_length=2)
    preferred_currency: str = Field(default="EUR", min_length=3, max_length=3)
    timezone: str = Field(default="Europe/Paris", min_length=2, max_length=100)


class LoginRequest(BaseModel):
    email: str = Field(min_length=3, max_length=255)
    password: str = Field(min_length=8, max_length=128)


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class ForgotPasswordRequest(BaseModel):
    email: str = Field(min_length=3, max_length=255)


class ForgotPasswordResponse(BaseModel):
    message: str


class ResetPasswordRequest(BaseModel):
    token: str = Field(min_length=24, max_length=512)
    password: str = Field(min_length=8, max_length=128)


class ResetPasswordResponse(BaseModel):
    message: str
