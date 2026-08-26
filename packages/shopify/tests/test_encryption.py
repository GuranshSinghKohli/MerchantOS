import base64
import secrets

import pytest
from merchantos_domain import StoreUninstalledError
from merchantos_shopify.encryption import TokenEncryptor


def test_round_trip_and_tombstone() -> None:
    key = base64.urlsafe_b64encode(secrets.token_bytes(32)).decode()
    enc = TokenEncryptor.from_urlsafe_key(key, "v1")
    blob = enc.encrypt("shpua_secret")
    assert b"shpua_secret" not in blob
    assert enc.decrypt(blob) == "shpua_secret"
    with pytest.raises(StoreUninstalledError):
        enc.decrypt(TokenEncryptor.tombstone())
