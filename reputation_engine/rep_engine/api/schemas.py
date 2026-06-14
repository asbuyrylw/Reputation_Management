"""Request models for the API. Responses are returned as plain dicts (the engine
already returns JSON-ready dict_row rows / aggregation dicts)."""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel


class LoginRequest(BaseModel):
    email: str
    password: str


class RejectRequest(BaseModel):
    notes: Optional[str] = None


class StatusRequest(BaseModel):
    status: str
    assignee: Optional[str] = None
    notes: Optional[str] = None


class ResumeRequest(BaseModel):
    approved: bool
    edited_response: Optional[str] = None
