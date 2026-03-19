"""
Shared slowapi limiter instance.
Extracted from api/main.py to break circular import:
  api/main.py → api/routes/* → api/main.py (limiter)
"""
import os
from slowapi import Limiter
from slowapi.util import get_remote_address

limiter = Limiter(
    key_func=get_remote_address,
    storage_uri=os.environ.get("REDIS_CACHE_URL", "redis://localhost:6379/1"),
)
