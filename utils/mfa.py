"""
Phase 6.5 — TOTP MFA using PyOTP.
Generates and verifies time-based one-time passwords for 2FA.
Secrets stored AES-256 encrypted in MongoDB.
"""
import base64
import io
import os
from typing import TYPE_CHECKING

import pyotp

from utils.encryption import encrypt, decrypt

if TYPE_CHECKING:
    pass

TOTP_ISSUER = os.getenv("TOTP_ISSUER", "SocialEntangler")
# Allow 1 step (30s) clock drift in each direction
TOTP_VALID_WINDOW = 1


def generate_totp_secret() -> str:
    """Generate a new random TOTP secret. Returns base32-encoded string."""
    return pyotp.random_base32()


def get_totp_uri(secret: str, user_email: str) -> str:
    """Return otpauth:// URI for QR code generation."""
    totp = pyotp.TOTP(secret)
    return totp.provisioning_uri(name=user_email, issuer_name=TOTP_ISSUER)


def verify_totp(encrypted_secret: str, code: str) -> bool:
    """
    Verify a 6-digit TOTP code against the user's encrypted secret.
    Returns True if code is valid within the clock-drift window.
    """
    try:
        secret = decrypt(encrypted_secret)
        totp = pyotp.TOTP(secret)
        return totp.verify(code, valid_window=TOTP_VALID_WINDOW)
    except Exception:
        return False


def encrypt_totp_secret(secret: str) -> str:
    """AES-256 encrypt the TOTP secret for storage in MongoDB."""
    return encrypt(secret)
