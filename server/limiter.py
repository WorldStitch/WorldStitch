"""Shared slowapi rate-limiter instance.

Imported by both server/app.py (to mount middleware) and route modules
(to apply per-endpoint limits) so there is only one Limiter object.
"""

from slowapi import Limiter
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address)
