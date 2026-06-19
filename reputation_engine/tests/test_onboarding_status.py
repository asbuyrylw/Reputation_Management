"""Getting-started checklist status (onboarding.status, derived from existing data)."""

from __future__ import annotations

from conftest import requires_db


@requires_db
def test_onboarding_status_reflects_data(fresh_schema):
    conn = fresh_schema
    from rep_engine import onboarding
    from rep_engine import prompts as p
    from rep_engine import competitor as cp
    bid = conn.execute(
        "INSERT INTO businesses (name, domain) VALUES ('Acme','a.com') RETURNING id"
    ).fetchone()["id"]
    conn.commit()

    s0 = onboarding.status(bid)
    assert s0["done"] == 0 and s0["complete"] is False
    assert s0["total"] == len(s0["steps"])
    # every step carries a label + an actionable href
    assert all(st["label"] and st["href"].startswith("/") for st in s0["steps"])

    # completing steps flips them done
    cp.register_competitor(bid, "Rival", "r.com")
    p.add_prompt(bid, "Is Acme legit?")
    conn.execute("INSERT INTO monitor_keywords (business_id, keyword, negative) VALUES (%s,'Acme',false)", (bid,))
    conn.commit()

    s1 = onboarding.status(bid)
    done = {st["key"] for st in s1["steps"] if st["done"]}
    assert {"competitors", "prompts", "keywords"} <= done
    assert s1["done"] == 3 and s1["complete"] is False
