"""Signed opaque candidate ids so callers can pick a subject without seeing SSN."""

from __future__ import annotations

import hashlib
import hmac
import os
from base64 import urlsafe_b64decode, urlsafe_b64encode


class CandidateTokenError(ValueError):
    """Raised when a candidate_id is missing, malformed, or tampered with."""


def _secret() -> bytes:
    """Return the HMAC key used to sign candidate ids.

    Returns:
        Key bytes from the app client secret or a local fallback.
    """
    raw = (
        os.getenv("DATABRICKS_CLIENT_SECRET")
        or os.getenv("DCSA_CANDIDATE_SECRET")
        or "dcsa-api-local-candidate-secret"
    )
    return raw.encode()


def sign_candidate_id(ssn: str) -> str:
    """Build an opaque, signed candidate id from an SSN.

    Args:
        ssn: Subject Social Security Number (digits only).

    Returns:
        URL-safe token of the form ``payload.signature``.
    """
    payload = urlsafe_b64encode(ssn.encode()).decode().rstrip("=")
    sig = hmac.new(_secret(), payload.encode(), hashlib.sha256).hexdigest()[:24]
    return f"{payload}.{sig}"


def ssn_from_candidate_id(candidate_id: str) -> str:
    """Verify a candidate id and recover the SSN.

    Args:
        candidate_id: Token previously issued by ``sign_candidate_id``.

    Returns:
        The original SSN.

    Raises:
        CandidateTokenError: If the token is invalid.
    """
    raw = (candidate_id or "").strip()
    if "." not in raw:
        raise CandidateTokenError("Invalid candidate_id")
    payload, sig = raw.rsplit(".", 1)
    expected = hmac.new(_secret(), payload.encode(), hashlib.sha256).hexdigest()[:24]
    if not hmac.compare_digest(sig, expected):
        raise CandidateTokenError("Invalid candidate_id")
    padding = "=" * (-len(payload) % 4)
    try:
        ssn = urlsafe_b64decode(payload + padding).decode()
    except Exception as exc:
        raise CandidateTokenError("Invalid candidate_id") from exc
    if not ssn:
        raise CandidateTokenError("Invalid candidate_id")
    return ssn
