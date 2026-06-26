"""Publishing package (Integrations Phase 2+).

Stateless adapters (`wordpress`, `ayrshare`, `google_business`) take a decrypted Connection +
normalized PublishPayload and do I/O through `http.request_json(guard_redirects=True)`, returning
a PublishResult. `runner.py` is the ONLY DB-touching piece: it claims network-grain targets,
decrypts via the vault, calls the adapter, and writes back redacted attempts + the live URL.
"""
