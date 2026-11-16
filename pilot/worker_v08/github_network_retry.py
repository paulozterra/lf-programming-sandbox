"""Bounded retries for temporary GitHub/Actions artifact transport failures.

Only retry safe reads. Never print a URL, signed query, token or response body.
"""
from __future__ import annotations

import socket
import time
import urllib.error


def transport_read(action, origin: str, *, sleep=time.sleep):
    """Retry HTTP 429/5xx and connection/timeouts at most three attempts."""
    if not isinstance(origin, str) or not origin.isidentifier():
        raise ValueError("GITHUB_TRANSPORT_ORIGIN_INVALID")
    for attempt in range(3):
        try:
            return action()
        except urllib.error.HTTPError as exc:
            status = int(exc.code)
            exc.close()
            if status != 429 and not 500 <= status <= 599:
                raise ValueError(f"GITHUB_HTTP_{status}:{origin}") from None
        except (urllib.error.URLError, TimeoutError, socket.timeout, ConnectionError):
            pass
        if attempt == 2:
            raise ValueError(f"GITHUB_TRANSITORIO:{origin}") from None
        sleep(2 ** attempt)
