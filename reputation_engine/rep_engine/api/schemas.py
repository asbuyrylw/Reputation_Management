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
    completed_on: Optional[str] = None  # YYYY-MM-DD real completion date (may be back-dated)


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


class InviteRequest(BaseModel):
    email: str
    full_name: Optional[str] = None
    org_role: str = "member"              # owner | admin | member
    org_id: Optional[int] = None          # admin only; org managers invite into their own org


class AcceptInviteRequest(BaseModel):
    token: str
    password: str


class ForgotPasswordRequest(BaseModel):
    email: str


class ResetPasswordRequest(BaseModel):
    token: str
    password: str


class CheckoutRequest(BaseModel):
    plan_code: str
    success_url: Optional[str] = None
    cancel_url: Optional[str] = None


class PortalRequest(BaseModel):
    return_url: Optional[str] = None


class GrantAccessRequest(BaseModel):
    business_id: int
    access_role: str = "viewer"


class CreateBusinessRequest(BaseModel):
    name: str
    domain: Optional[str] = None
    services: Optional[str] = None        # comma-joined service keywords (edited as tags in the UI)
    industry: Optional[str] = None        # the vertical, distinct from the specific services
    goal: Optional[str] = None
    contested_terms: Optional[str] = None
    geo: Optional[str] = None             # "Areas served" in the UI
    owned_domains: Optional[list[str]] = None  # extra web properties the business owns (citation = owned)
    org_id: Optional[int] = None          # organization that owns this business


class UpdateBusinessRequest(BaseModel):
    name: Optional[str] = None
    domain: Optional[str] = None
    services: Optional[str] = None
    industry: Optional[str] = None
    goal: Optional[str] = None
    contested_terms: Optional[str] = None
    geo: Optional[str] = None
    regulatory_profile: Optional[dict] = None   # {firm_type, disclosures[], crd, notes}
    owned_domains: Optional[list[str]] = None   # extra web properties the business owns


class IngestSignalRequest(BaseModel):
    source: str               # tool name, e.g. "siteguru"
    signal_type: str          # technical_seo|keywords|serp_rank|backlinks|brand|visitors|other
    content: str              # the pasted / uploaded report text
