"""Connections vault package (Integrations Phase 1).

The per-tenant credential layer beneath `social_presence`: OAuth tokens, WordPress
application-passwords, and Ayrshare profile-keys stored as Fernet ciphertext. `vault` is the
ONLY module that imports `rep_engine.crypto` (CI grep-asserted); `oauth` runs the handshake;
`providers/*` do provider-specific token exchange/verify, all I/O via netguard/http.
"""
