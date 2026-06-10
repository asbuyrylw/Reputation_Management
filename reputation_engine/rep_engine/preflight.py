"""
Reputation Crowding-Out Engine -- First-Live-Run Preflight
==========================================================
Run this BEFORE the first real audit. It validates everything that can fail on a
live run -- WITHOUT spending a full audit's worth of API budget. It makes at most
ONE tiny probe call per configured engine to confirm the request/response shape
(the PH 9-12 unknowns), then reports a clear go / no-go.

    python -m rep_engine.preflight --business-id 1

Exit code 0 = ready. Non-zero = something to fix (printed). Safe to run repeatedly.
"""

from __future__ import annotations

import argparse
import sys

try:
    from . import ai_state_audit as m
    from . import cost
    from . import db as _db
except ImportError:  # pragma: no cover
    import ai_state_audit as m  # type: ignore
    import cost  # type: ignore
    import db as _db  # type: ignore

GREEN, RED, YEL, RST = "\033[92m", "\033[91m", "\033[93m", "\033[0m"


def ok(msg): print(f"{GREEN}  [OK]{RST} {msg}")
def warn(msg): print(f"{YEL}  [! ]{RST} {msg}")
def bad(msg): print(f"{RED}  [X ]{RST} {msg}")


def check_config() -> bool:
    print("0. Configuration validation")
    try:
        from . import config
    except ImportError:  # pragma: no cover
        import config  # type: ignore
    passed, msgs = config.validate_or_explain()
    for msg in msgs:
        if msg.startswith("configured engines"):
            ok(msg)
        elif passed:
            ok(msg)
        else:
            warn(msg)
    if passed and not msgs:
        ok("configuration valid")
    return passed


def check_db() -> bool:
    print("1. Database")
    try:
        with m.db() as conn:
            conn.execute("SELECT 1")
        ok(f"connected: {_db.DB_DSN.split('@')[-1]}")
    except Exception as e:  # noqa: BLE001
        bad(f"cannot connect to REP_DB_DSN: {e}")
        return False
    # schema present?
    try:
        with m.db() as conn:
            for t in ["businesses", "audit_runs", "answers"]:
                conn.execute(f"SELECT 1 FROM {t} LIMIT 1")
        ok("core tables present")
    except Exception:  # noqa: BLE001
        bad("core tables missing -- run `alembic upgrade head` (or `make migrate`)")
        return False
    return True


def check_keys() -> dict:
    print("2. API keys / orchestrator")
    status = {}
    pairs = [("anthropic", m.ANTHROPIC_API_KEY, "YOUR_ANTHROPIC"),
             ("openai", m.OPENAI_API_KEY, "YOUR_OPENAI"),
             ("perplexity", m.PERPLEXITY_API_KEY, "YOUR_PERPLEXITY"),
             ("gemini", m.GEMINI_API_KEY, "YOUR_GEMINI")]
    for name, val, placeholder in pairs:
        configured = placeholder not in val
        status[name] = configured
        (ok if configured else warn)(f"{name}: {'configured' if configured else 'not set (will be skipped)'}")
    if not any(status.values()):
        bad("no API keys configured -- at least one answer engine is required")
    orch = m.ORCHESTRATOR
    if status.get(orch):
        ok(f"orchestrator = {orch} (key present)")
    else:
        bad(f"orchestrator = {orch} but its key is not set -- gap model/scoring will be empty")
    return status


def probe_engine(engine, label: str) -> bool:
    """One tiny call to confirm the live request/response shape (PH 9-12)."""
    try:
        res = engine.answer("Reply with the single word: ok.")
        if res.get("failed"):
            bad(f"{label}: call failed -- {res.get('error')}")
            return False
        if res.get("skipped"):
            warn(f"{label}: skipped (no key)")
            return True
        txt = (res.get("text") or "").strip()
        if txt:
            ok(f"{label}: live response shape verified ({txt[:40]!r})")
            return True
        warn(f"{label}: returned empty text -- check response parsing (PH 9-12)")
        return False
    except Exception as e:  # noqa: BLE001
        bad(f"{label}: exception -- {e}")
        return False


def check_engines(status: dict) -> bool:
    print("3. Live engine probes (one cheap call each)")
    any_ok = False
    probes = [
        (m.PerplexityEngine(), "perplexity", "perplexity"),
        (m.OpenAISearchEngine(), "openai_search", "openai"),
        (m.AnthropicEngine(), "anthropic", "anthropic"),
        (m.GeminiEngine(), "gemini", "gemini"),
    ]
    for eng, label, keyname in probes:
        if not status.get(keyname):
            continue
        if probe_engine(eng, label):
            any_ok = True
    if not any_ok:
        bad("no engine returned a usable response -- fix before running a full audit")
    return any_ok


def check_orchestrator_json() -> bool:
    print("4. Orchestrator structured-output probe")
    try:
        out = m.orchestrator_json("Return strict JSON only.",
                                  'Return {"status":"ok"} and nothing else.')
        if out.get("status") == "ok":
            ok("orchestrator returns parseable JSON (gap model + scoring will work)")
            return True
        warn(f"orchestrator JSON came back unexpected: {out} -- scoring may be degraded")
        return False
    except Exception as e:  # noqa: BLE001
        bad(f"orchestrator JSON probe failed: {e}")
        return False


def check_budget(business_id: int) -> bool:
    print("5. Budget guard")
    try:
        with m.db() as conn:
            cfg = conn.execute("SELECT monthly_budget_usd FROM business_config WHERE business_id=%s",
                               (business_id,)).fetchone()
        if cfg:
            ok(f"monthly budget cap set: ${cfg['monthly_budget_usd']}")
        else:
            warn("no business_config row -- defaults will apply (budget $50). Set one to control spend.")
        spent = cost.month_spend(business_id)
        ok(f"spent this month so far: ${spent:.2f}")
        return True
    except Exception as e:  # noqa: BLE001
        warn(f"could not read budget (non-fatal): {e}")
        return True


def main() -> None:
    ap = argparse.ArgumentParser(description="Preflight check before the first live run")
    ap.add_argument("--business-id", type=int, default=1)
    args = ap.parse_args()

    print("=" * 64)
    print(" Reputation Engine -- First-Live-Run Preflight")
    print("=" * 64)
    check_config()  # prints config status (advisory; readiness is gated on db/engines/json below)
    db_ok = check_db()
    status = check_keys()
    eng_ok = check_engines(status) if any(status.values()) else False
    json_ok = check_orchestrator_json() if status.get(m.ORCHESTRATOR) else False
    check_budget(args.business_id)

    print("-" * 64)
    ready = db_ok and eng_ok and json_ok
    if ready:
        print(f"{GREEN} READY{RST} -- safe to run:  python -m rep_engine.orchestrator run ...")
        sys.exit(0)
    else:
        print(f"{RED} NOT READY{RST} -- resolve the [X] items above, then re-run preflight.")
        sys.exit(1)


if __name__ == "__main__":
    main()
