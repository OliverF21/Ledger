"""
Security utilities for encrypting/decrypting Plaid access tokens.
Uses Fernet (AES-128-CBC with HMAC) for symmetric encryption.
"""

import os
from cryptography.fernet import Fernet

# Get encryption key from environment
ENCRYPTION_KEY = os.getenv("ENCRYPTION_KEY")

if not ENCRYPTION_KEY:
    raise ValueError("ENCRYPTION_KEY not set in environment. Generate one with: python -c \"from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())\"")

cipher = Fernet(ENCRYPTION_KEY.encode())


def encrypt_token(token: str) -> str:
    """
    Encrypt a Plaid access token using Fernet.

    Args:
        token: Plain-text access token from Plaid

    Returns:
        Encrypted token (bytes decoded to string)
    """
    encrypted = cipher.encrypt(token.encode())
    return encrypted.decode()


def decrypt_token(encrypted_token: str) -> str:
    """
    Decrypt a Plaid access token.

    Args:
        encrypted_token: Encrypted token string from database

    Returns:
        Plain-text access token (ready for Plaid API calls)
    """
    decrypted = cipher.decrypt(encrypted_token.encode())
    return decrypted.decode()
