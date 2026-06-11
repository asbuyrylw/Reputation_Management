"""The opt-in wiring of the agentic graphs into the orchestrator run steps:
default-off, env-gated, lazy-imported, and a graph failure can't break the cycle."""

from __future__ import annotations

_FLAGS = ("AGENT_ROOTCAUSE_IN_CYCLE", "AGENT_DISCOVERY_IN_CYCLE",
          "AGENT_INCIDENT_IN_CYCLE", "AGENT_REMEDIATION_IN_CYCLE")


class _FakeRS:
    def __init__(self):
        self.keys = []

    def step(self, key, fn, desc=""):
        self.keys.append(key)
        fn()   # execute the step (lazy-imports + runs the agent)


def test_no_agentic_steps_by_default(monkeypatch):
    from rep_engine import orchestrator as o
    for f in _FLAGS:
        monkeypatch.delenv(f, raising=False)
    rs = _FakeRS()
    o._maybe_agentic_steps(rs, 1)
    assert rs.keys == []                       # opt-in: nothing added unless enabled


def test_enabled_agentic_steps_added_and_run(monkeypatch):
    from rep_engine import agent_incident as ai
    from rep_engine import agent_rootcause as ar
    from rep_engine import orchestrator as o
    for f in _FLAGS:
        monkeypatch.delenv(f, raising=False)
    monkeypatch.setenv("AGENT_ROOTCAUSE_IN_CYCLE", "1")
    monkeypatch.setenv("AGENT_INCIDENT_IN_CYCLE", "true")
    ran = []
    monkeypatch.setattr(ar, "investigate", lambda bid: ran.append(("rc", bid)) or {"ok": True})
    monkeypatch.setattr(ai, "scan", lambda bid: ran.append(("inc", bid)) or [])
    rs = _FakeRS()
    o._maybe_agentic_steps(rs, 42)
    assert rs.keys == ["root_cause", "incident_scan"]    # only the enabled ones, in order
    assert ("rc", 42) in ran and ("inc", 42) in ran      # called with the right business id


def test_agentic_step_failure_does_not_break_cycle(monkeypatch):
    from rep_engine import agent_rootcause as ar
    from rep_engine import orchestrator as o
    for f in _FLAGS:
        monkeypatch.delenv(f, raising=False)
    monkeypatch.setenv("AGENT_ROOTCAUSE_IN_CYCLE", "yes")

    def _boom(bid):
        raise RuntimeError("graph exploded")

    monkeypatch.setattr(ar, "investigate", _boom)
    rs = _FakeRS()
    o._maybe_agentic_steps(rs, 1)              # must NOT raise -- _safe_agentic swallows it
    assert rs.keys == ["root_cause"]
