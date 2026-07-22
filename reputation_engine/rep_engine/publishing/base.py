"""
Publisher protocol + value types (Integrations Phase 2)
=======================================================
Adapters are stateless: they receive a decrypted `Connection` + normalized `PublishPayload`,
do I/O through `http.request_json(guard_redirects=True)`, and return a `PublishResult`. They
NEVER touch the DB -- `runner.py` owns all reads/writes. Because fan-out is network-grain (one
target row per network), each `publish()` handles exactly one network and returns one result;
there is no `partial` for the runner to explode.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal, Optional, Protocol, runtime_checkable

PayloadKind = Literal["article", "social", "link"]


@dataclass(frozen=True)
class Connection:
    id: int
    business_id: int
    provider: str          # wordpress | ayrshare | google_business
    channel: str           # registry channel key
    access_token: str      # decrypted in the runner; in-process only, never logged/persisted
    refresh_token: Optional[str] = None
    config: dict = field(default_factory=dict)  # site_url, wp_user, profile_key, location_id, ...


@dataclass(frozen=True)
class PublishPayload:
    kind: PayloadKind
    title: Optional[str] = None
    body_html: Optional[str] = None
    body_markdown: Optional[str] = None
    tags: list = field(default_factory=list)
    categories: list = field(default_factory=list)
    text: Optional[str] = None
    link_url: Optional[str] = None
    media: list = field(default_factory=list)
    scheduled_at: Optional[str] = None   # ISO8601 UTC; None = publish now
    network: str = "_"
    idempotency_key: str = ""
    schema_jsonld: Optional[str] = None  # a <script type="application/ld+json"> block to inject (Phase 5B)


@dataclass(frozen=True)
class PublishResult:
    status: Literal["live", "scheduled", "failed"]
    external_url: Optional[str] = None
    external_id: Optional[str] = None
    error: Optional[str] = None
    retryable: bool = False
    retry_after_s: Optional[int] = None
    http_status: Optional[int] = None
    # set when the failure is an auth rejection (401/invalid_grant) -> runner revokes the connection
    auth_failed: bool = False


@dataclass(frozen=True)
class Capability:
    article: bool = False
    social: bool = False
    link: bool = False
    schedule: bool = False
    draft_then_publish: bool = False


@runtime_checkable
class Publisher(Protocol):
    provider: str

    def capabilities(self, conn: Connection) -> Capability: ...
    def publish(self, conn: Connection, payload: PublishPayload) -> PublishResult: ...
