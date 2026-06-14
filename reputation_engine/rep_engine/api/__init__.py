"""
rep_engine.api -- a read+write FastAPI layer over the verified Reputation Engine.

PURELY ADDITIVE: this package never modifies the CLI engine. It reuses db.db()
and the engine's existing aggregation functions, and adds auth + multi-tenancy +
a background-job runner. Hard rules (see the console plan):
  * no LLM spend inside a request -- engine-spending work runs as a background job
    so cost.over_budget and audit()'s advisory lock stay the backstops;
  * human gates (draft/incident/reply approval) only advance via explicit endpoints;
  * every scoped route enforces business_id authorization.

Run:  uvicorn rep_engine.api.main:app --reload    (needs REP_DB_DSN + JWT_SECRET)
"""
