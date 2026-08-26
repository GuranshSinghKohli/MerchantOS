from __future__ import annotations

import base64
import secrets

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from merchantos_domain import StoreUninstalledError

_NONCE_LEN = 12
_TOMBSTONE = b"\x00" * 16


class TokenEncryptor:
    """Local envelope: AES-256-GCM with a versioned DEK from env/Secrets Manager.

    Production should wrap this DEK with KMS. Ciphertext is never logged.
    """

    def __init__(self, key_material: bytes, key_version: str) -> None:
        if len(key_material) != 32:
            raise ValueError("TOKEN_ENCRYPTION_KEY must decode to 32 bytes")
        self._aes = AESGCM(key_material)
        self.key_version = key_version

    @classmethod
    def from_urlsafe_key(cls, key_b64: str, key_version: str) -> TokenEncryptor:
        return cls(base64.urlsafe_b64decode(key_b64), key_version)

    def encrypt(self, plaintext: str) -> bytes:
        nonce = secrets.token_bytes(_NONCE_LEN)
        return nonce + self._aes.encrypt(nonce, plaintext.encode(), None)

    def decrypt(self, blob: bytes) -> str:
        if not blob or blob == _TOMBSTONE:
            raise StoreUninstalledError("Shopify token is not decryptable")
        nonce, ciphertext = blob[:_NONCE_LEN], blob[_NONCE_LEN:]
        return self._aes.decrypt(nonce, ciphertext, None).decode()

    @staticmethod
    def tombstone() -> bytes:
        return _TOMBSTONE
