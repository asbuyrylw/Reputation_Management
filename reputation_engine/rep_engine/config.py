"""
Config -- validated settings for the Reputation Engine (Pydantic v2).

Centralizes every environment variable the engine reads, validates types and
ranges, and surfaces a single clear error at startup instead of a cryptic failure
deep inside a run. Import `settings()` to get a validated Settings object; call
`validate_or_explain()` (used by preflight) for a human-readable readiness report.

Nothing here makes network calls -- it only checks that configuration is coherent
(e.g. the chosen orchestrator has a key set, thresholds are in range, the DSN is
well-formed). Live connectivity is still checked by preflight.
"""

from __future__ import annotations

import os
from typing import Literal, Optional

from pydantic import BaseModel, Field, field_validator, model_validator


class Settings(BaseModel):
    # --- database ---
    rep_db_dsn: str = Field(..., description="Postgres connection string")
    output_dir: str = "output"

    # --- orchestrator + keys ---
    orchestrator: Literal["anthropic", "openai"] = "anthropic"
    anthropic_api_key: str = "YOUR_ANTHROPIC_KEY"
    openai_api_key: str = "YOUR_OPENAI_KEY"
    perplexity_api_key: str = "YOUR_PERPLEXITY_KEY"
    gemini_api_key: str = "YOUR_GEMINI_KEY"

    # --- NotebookLM API (rich-media generation) ---
    # Falls back to GEMINI_API_KEY when not set; both use the same Google AI Studio key.
    notebooklm_api_key: str = ""
    # Base URL for the NotebookLM / Semantic Retrieval API (override for VPC endpoints).
    notebooklm_base_url: str = "https://generativelanguage.googleapis.com/v1beta"
    # Rich-media asset types to generate when AGENT_RICH_MEDIA_IN_CYCLE=1.
    # Comma-separated list; empty string means all types.
    rich_media_types: str = ""

    # --- crawler ---
    crawl_respect_robots: bool = True
    crawl_use_pyseo: bool = True
    crawl_ua: str = "ReputationEngineBot/1.0 (+audit)"

    # --- content generator ---
    content_quality_threshold: float = Field(0.75, ge=0.0, le=1.0)
    content_max_revisions: int = Field(2, ge=0, le=10)

    # --- timeline estimator ---
    dominance_target: float = Field(0.6, ge=0.0, le=1.0)
    base_monthly_gain: float = Field(0.12, gt=0.0, le=1.0)

    @field_validator("rep_db_dsn")
    @classmethod
    def _dsn_shape(cls, v: str) -> str:
        if not v or not v.startswith(("postgresql://", "postgres://")):
            raise ValueError("REP_DB_DSN must be a postgresql:// connection string")
        if "USER:PASSWORD" in v:
            raise ValueError("REP_DB_DSN still contains the placeholder USER:PASSWORD")
        return v

    def key_for(self, provider: str) -> str:
        return getattr(self, f"{provider}_api_key", "")

    def orchestrator_key_set(self) -> bool:
        key = self.key_for(self.orchestrator)
        return bool(key) and "YOUR_" not in key

    def configured_engines(self) -> list[str]:
        out = []
        for p in ("anthropic", "openai", "perplexity", "gemini"):
            k = self.key_for(p)
            if k and "YOUR_" not in k:
                out.append(p)
        return out

    @model_validator(mode="after")
    def _coherence(self) -> "Settings":
        # thresholds sanity: dominance target should exceed a trivial value
        if self.dominance_target < 0.1:
            raise ValueError("DOMINANCE_TARGET < 0.1 is implausibly low; check configuration")
        return self


def _as_bool(v: Optional[str], default: bool) -> bool:
    if v is None:
        return default
    return v.strip().lower() not in ("0", "false", "no", "")


def load_settings(env: Optional[dict] = None) -> Settings:
    """Build Settings from the environment (or a provided dict). Raises
    pydantic.ValidationError with a clear message if anything is invalid."""
    e = env if env is not None else os.environ
    return Settings(
        rep_db_dsn=e.get("REP_DB_DSN", ""),
        output_dir=e.get("REP_OUTPUT_DIR", "output"),
        orchestrator=e.get("ORCHESTRATOR", "anthropic"),
        anthropic_api_key=e.get("ANTHROPIC_API_KEY", "YOUR_ANTHROPIC_KEY"),
        openai_api_key=e.get("OPENAI_API_KEY", "YOUR_OPENAI_KEY"),
        perplexity_api_key=e.get("PERPLEXITY_API_KEY", "YOUR_PERPLEXITY_KEY"),
        gemini_api_key=e.get("GEMINI_API_KEY", "YOUR_GEMINI_KEY"),
        notebooklm_api_key=e.get("NOTEBOOKLM_API_KEY", ""),
        notebooklm_base_url=e.get(
            "NOTEBOOKLM_BASE_URL",
            "https://generativelanguage.googleapis.com/v1beta",
        ),
        rich_media_types=e.get("RICH_MEDIA_TYPES", ""),
        crawl_respect_robots=_as_bool(e.get("CRAWL_RESPECT_ROBOTS"), True),
        crawl_use_pyseo=_as_bool(e.get("CRAWL_USE_PYSEO"), True),
        crawl_ua=e.get("CRAWL_UA", "ReputationEngineBot/1.0 (+audit)"),
        content_quality_threshold=float(e.get("CONTENT_QUALITY_THRESHOLD", "0.75")),
        content_max_revisions=int(e.get("CONTENT_MAX_REVISIONS", "2")),
        dominance_target=float(e.get("DOMINANCE_TARGET", "0.6")),
        base_monthly_gain=float(e.get("BASE_MONTHLY_GAIN", "0.12")),
    )


_cached: Optional[Settings] = None


def settings(reload: bool = False) -> Settings:
    """Return validated settings (cached). Raises on invalid config."""
    global _cached
    if _cached is None or reload:
        _cached = load_settings()
    return _cached


def validate_or_explain(env: Optional[dict] = None) -> tuple[bool, list[str]]:
    """Non-raising validation for preflight/CLI. Returns (ok, messages)."""
    msgs: list[str] = []
    try:
        s = load_settings(env)
    except Exception as e:  # noqa: BLE001 -- pydantic ValidationError or coercion error
        # pydantic errors are multi-line; surface them as-is
        for line in str(e).splitlines():
            line = line.strip()
            if line and not line.startswith("For further information"):
                msgs.append(line)
        return False, msgs
    # coherent types, now check operational coherence (warnings, not hard fails)
    if not s.orchestrator_key_set():
        msgs.append(f"orchestrator='{s.orchestrator}' but its API key is not set "
                    f"-- gap model, scoring, and content generation will be empty")
    engines = s.configured_engines()
    if not engines:
        msgs.append("no answer-engine API keys configured -- at least one is required for a live audit")
    else:
        msgs.append(f"configured engines: {', '.join(engines)}")
    ok = s.orchestrator_key_set() and bool(engines)
    return ok, msgs
