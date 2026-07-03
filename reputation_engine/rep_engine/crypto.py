"""
Reputation Crowding-Out Engine -- reversible crypto-at-rest (Integrations Phase 0)
=================================================================================
The ONLY reversible-crypto seam in the codebase. OAuth tokens, WordPress application
passwords, and Ayrshare profile-keys are stored as Fernet ciphertext in
`platform_connections.access_token_enc` / `refresh_token_enc`; the symmetric key lives
in the environment (`TOKEN_ENC_KEY`), never in Postgres -- which is why we cannot use
`pgcrypto`. `connections/vault.py` is the ONLY module that imports this (CI grep-asserted),
so a single audited path touches plaintext secrets.

`MultiFernet` gives us key rotation: `TOKEN_ENC_KEY` may be a comma-separated list; keys[0]
encrypts, every key can decrypt. `rotate_token_keys()` (CLI/job) re-encrypts every stored
secret under keys[0] so a retired key can be dropped.

Operational posture (mirrors the Stripe-key handling): a missing key is NOT a hard boot
failure -- `health()` reports `degraded` and the connect UI stays disabled -- but the key is
asserted `!= JWT_SECRET` so a JWT-secret leak can never also decrypt the vault.

Generate a key:
    python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
"""

from __future__ import annotations

import os
from functools import lru_cache
from typing import Optional

try:  # cryptography is an integrations dependency; degrade gracefully if absent at import time.
    from cryptography.fernet import Fernet, MultiFernet, InvalidToken
    _HAVE_CRYPTO = True
except Exception:  # pragma: no cover -- surfaced via health() / configured()
    Fernet = MultiFernet = None  # type: ignore
    class InvalidToken(Exception):  # type: ignore
        ...
    _HAVE_CRYPTO = False


class CryptoNotConfigured(RuntimeError):
    """Raised when an encrypt/decrypt is attempted but TOKEN_ENC_KEY is unusable."""


_GEN_HINT = (
    "TOKEN_ENC_KEY is not set. Generate one with: "
    "python -c \"from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())\""
)


def _keys() -> list[str]:
    raw = os.getenv("TOKEN_ENC_KEY", "").strip()
    return [k.strip() for k in raw.split(",") if k.strip()]


@lru_cache(maxsize=1)
def _fernet() -> "MultiFernet":
    if not _HAVE_CRYPTO:
        raise CryptoNotConfigured("the 'cryptography' package is not installed (pip install 'cryptography>=42').")
    keys = _keys()
    if not keys:
        raise CryptoNotConfigured(_GEN_HINT)
    # Separate blast radius: a leaked JWT_SECRET must not also decrypt the token vault.
    jwt = os.getenv("JWT_SECRET", "")
    if jwt and jwt in keys:
        raise CryptoNotConfigured("TOKEN_ENC_KEY must not equal JWT_SECRET (separate blast radius).")
    try:
        return MultiFernet([Fernet(k.encode()) for k in keys])
    except Exception as e:  # noqa: BLE001 -- malformed key material
        raise CryptoNotConfigured(f"TOKEN_ENC_KEY is malformed (not valid Fernet key material): {e}") from e


def configured() -> bool:
    """True iff a usable key is present (no exception thrown). Cheap; used by health + UI gating."""
    try:
        _fernet()
        return True
    except CryptoNotConfigured:
        return False


def health() -> dict:
    """Startup/`/health` probe. Never raises -- reports degraded instead (Stripe-parity)."""
    if not _HAVE_CRYPTO:
        return {"ok": False, "degraded": True, "reason": "cryptography package not installed"}
    keys = _keys()
    if not keys:
        return {"ok": False, "degraded": True, "reason": "TOKEN_ENC_KEY not set"}
    jwt = os.getenv("JWT_SECRET", "")
    if jwt and jwt in keys:
        return {"ok": False, "degraded": True, "reason": "TOKEN_ENC_KEY equals JWT_SECRET"}
    try:
        _fernet()
    except CryptoNotConfigured as e:
        return {"ok": False, "degraded": True, "reason": str(e)}
    return {"ok": True, "degraded": False, "keys": len(keys)}


def encrypt(plaintext: Optional[str]) -> Optional[str]:
    """Encrypt a secret to Fernet ciphertext (str). None/empty -> None (so NULL columns stay NULL)."""
    if plaintext is None or plaintext == "":
        return None
    return _fernet().encrypt(plaintext.encode("utf-8")).decode("ascii")


def decrypt(ciphertext: Optional[str]) -> Optional[str]:
    """Decrypt Fernet ciphertext back to the plaintext secret. None -> None.

    Raises CryptoNotConfigured if the key is unusable, or InvalidToken if the ciphertext does
    not verify under any current key (e.g. rotated out without re-encrypting)."""
    if ciphertext is None or ciphertext == "":
        return None
    return _fernet().decrypt(ciphertext.encode("ascii")).decode("utf-8")


def rotate_token_keys() -> dict:
    """Re-encrypt every stored secret under keys[0]. Run after prepending a new key to
    TOKEN_ENC_KEY; afterwards the retired trailing key(s) can be dropped. Imported lazily to
    keep the crypto module free of DB deps."""
    f = _fernet()
    rotated = 0
    failed = 0
    try:
        from .db import db  # local import: crypto.py must not hard-depend on db
    except ImportError:  # pragma: no cover
        from db import db  # type: ignore
    with db() as conn:
        rows = conn.execute(
            "SELECT id, access_token_enc, refresh_token_enc FROM platform_connections "
            "WHERE access_token_enc IS NOT NULL OR refresh_token_enc IS NOT NULL"
        ).fetchall()
        for r in rows:
            try:
                new_a = (f.rotate(r["access_token_enc"].encode("ascii")).decode("ascii")
                         if r["access_token_enc"] else None)
                new_r = (f.rotate(r["refresh_token_enc"].encode("ascii")).decode("ascii")
                         if r["refresh_token_enc"] else None)
            except (InvalidToken, Exception):  # noqa: BLE001 -- skip un-rotatable rows, keep going
                failed += 1
                continue
            conn.execute(
                "UPDATE platform_connections SET access_token_enc=%s, refresh_token_enc=%s, "
                "updated_at=now() WHERE id=%s", (new_a, new_r, r["id"]))
            rotated += 1
        conn.commit()
    return {"rotated": rotated, "failed": failed}


if __name__ == "__main__":  # pragma: no cover
    import json
    print(json.dumps(health(), indent=2))
