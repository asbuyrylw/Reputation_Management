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


class CreateUserRequest(BaseModel):
    email: str
    password: str
    full_name: Optional[str] = None
    role: str = "client"
    org_id: Optional[int] = None          # org the user belongs to
    org_role: str = "member"              # owner | admin | member


class CreateOrganizationRequest(BaseModel):
    name: str


class AssignSubscriptionRequest(BaseModel):
    plan_code: str
    status: str = "trialing"      # trialing | active | past_due | canceled


class GrantAccessRequest(BaseModel):
    business_id: int
    access_role: str = "viewer"


class CreateBusinessRequest(BaseModel):
    name: str
    domain: Optional[str] = None
    services: Optional[str] = None
    goal: Optional[str] = None
    contested_terms: Optional[str] = None
    geo: Optional[str] = None
    org_id: Optional[int] = None          # organization that owns this business


class UpdateBusinessRequest(BaseModel):
    name: Optional[str] = None
    domain: Optional[str] = None
    services: Optional[str] = None
    goal: Optional[str] = None
    contested_terms: Optional[str] = None
    geo: Optional[str] = None


class IngestSignalRequest(BaseModel):
    source: str               # tool name, e.g. "siteguru"
    signal_type: str          # technical_seo|keywords|serp_rank|backlinks|brand|visitors|other
    content: str              # the pasted / uploaded report text
