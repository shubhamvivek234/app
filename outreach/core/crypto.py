"""
Phase 2: Cryptographic utilities for encrypting and decrypting sensitive LinkedIn
session tokens (li_at, JSESSIONID) and proxy credentials using AES-256 Fernet.
"""
from utils.encryption import encrypt as _fernet_encrypt, decrypt as _fernet_decrypt


def encrypt_secret(secret_text: str) -> str:
    """Encrypts plaintext secret into URL-safe base64 ciphertext."""
    if not secret_text:
        return ""
    return _fernet_encrypt(secret_text)


def decrypt_secret(ciphertext: str) -> str:
    """Decrypts ciphertext back into plaintext secret."""
    if not ciphertext:
        return ""
    return _fernet_decrypt(ciphertext)
