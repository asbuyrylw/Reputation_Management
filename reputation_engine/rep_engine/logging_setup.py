"""
Structured logging -- run-scoped, filterable logs for multi-client operation.

Two modes:
  - default human format (unchanged feel) with an optional [biz=.. run=..] prefix
  - JSON lines (set REP_LOG_JSON=1) for ingestion into log tooling

Use get_logger(name) as a drop-in for logging.getLogger. Use bind(business_id=,
run_id=) to attach context that then appears on every subsequent record from any
logger -- so a whole run's lines can be filtered by run id even across modules.

Kept dependency-free (stdlib logging only).
"""

from __future__ import annotations

import json
import logging
import os
import sys
from contextvars import ContextVar
from typing import Any

_JSON = os.getenv("REP_LOG_JSON", "0") not in ("0", "false", "", "no")
_LEVEL = os.getenv("REP_LOG_LEVEL", "INFO").upper()

# context shared across all loggers/modules in this process for the current run
_ctx: ContextVar[dict] = ContextVar("rep_log_ctx", default={})


def bind(**kwargs: Any) -> None:
    """Attach context (e.g. business_id, run_id) to all subsequent log records."""
    cur = dict(_ctx.get())
    cur.update({k: v for k, v in kwargs.items() if v is not None})
    _ctx.set(cur)


def clear() -> None:
    _ctx.set({})


class _ContextFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.ctx = dict(_ctx.get())
        return True


class _HumanFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        ctx = getattr(record, "ctx", {}) or {}
        prefix = ""
        if ctx:
            bits = " ".join(f"{k}={v}" for k, v in ctx.items())
            prefix = f"[{bits}] "
        base = f"{self.formatTime(record, '%Y-%m-%d %H:%M:%S')} {record.levelname} {record.name}: "
        return base + prefix + record.getMessage()


class _JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "ts": self.formatTime(record, "%Y-%m-%dT%H:%M:%S"),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        ctx = getattr(record, "ctx", {}) or {}
        payload.update(ctx)
        return json.dumps(payload, default=str)


class _DynamicStderrHandler(logging.StreamHandler):
    """StreamHandler that always targets the CURRENT sys.stderr. We configure logging
    once per process, but a plain StreamHandler binds sys.stderr at creation -- which
    silences anything that later swaps stderr (e.g. pytest's capsys). Resolving the
    stream at emit time keeps output going wherever stderr currently points."""

    def __init__(self) -> None:
        logging.Handler.__init__(self)   # skip StreamHandler.__init__ (it sets self.stream)

    @property
    def stream(self):  # type: ignore[override]
        return sys.stderr

    @stream.setter
    def stream(self, _value):  # noqa: D401 -- always use current sys.stderr; ignore sets
        pass


_configured = False


def configure() -> None:
    global _configured
    if _configured:
        return
    handler = _DynamicStderrHandler()
    handler.addFilter(_ContextFilter())
    handler.setFormatter(_JsonFormatter() if _JSON else _HumanFormatter())
    root = logging.getLogger()
    # replace existing handlers so we don't double-print with basicConfig
    root.handlers = [handler]
    root.setLevel(getattr(logging, _LEVEL, logging.INFO))
    _configured = True


def get_logger(name: str) -> logging.Logger:
    configure()
    return logging.getLogger(name)
