"""Connection providers: per-platform token exchange / credential verification.

All outbound I/O goes through `rep_engine.http.request_json(..., guard_redirects=True)` /
`netguard.assert_url_allowed`, with fixed provider hosts pinned and tenant-supplied hosts
(WordPress site_url) restricted to HTTPS + IP-validated. No raw `requests.*` here.
"""
