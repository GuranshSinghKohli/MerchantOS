import secrets
import time
from uuid import UUID


def uuid7() -> UUID:
    """RFC 9562 UUIDv7 without extra dependencies."""
    unix_ts_ms = int(time.time() * 1000) & ((1 << 48) - 1)
    rand_a = secrets.randbits(12)
    rand_b = secrets.randbits(62)
    value = (unix_ts_ms << 80) | (0x7 << 76) | (rand_a << 64) | (0b10 << 62) | rand_b
    return UUID(int=value)
