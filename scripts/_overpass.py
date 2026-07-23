"""Shared Overpass API POST helper with bounded retries for transient failures."""

import time
from typing import Protocol

try:
    import requests
except ImportError:
    requests = None  # type: ignore[assignment]

_MISSING_REQUESTS = (
    "'requests' package not installed; run: pip install 'bvlos-sim[scripts]'"
)

_ATTEMPTS = 3
_BACKOFF_S = (2.0, 8.0)
_RETRY_STATUS_CODES = frozenset({429, 504})


class OverpassError(RuntimeError):
    """Raised when an Overpass request still fails after all retry attempts."""


class _Response(Protocol):
    status_code: int

    def raise_for_status(self) -> None: ...

    def json(self) -> object: ...


def post_with_retry(
    url: str,
    *,
    data: dict[str, str],
    headers: dict[str, str],
    timeout: float,
) -> _Response:
    """POST to an Overpass endpoint, retrying transient failures.

    Retries HTTP 429/504 responses and connection errors up to three attempts
    with exponential backoff (2 s, then 8 s). Other HTTP errors raise
    immediately via raise_for_status.
    """
    if requests is None:
        raise RuntimeError(_MISSING_REQUESTS)
    last_failure = "unknown failure"
    for attempt in range(_ATTEMPTS):
        if attempt > 0:
            time.sleep(_BACKOFF_S[attempt - 1])
        try:
            response = requests.post(url, data=data, headers=headers, timeout=timeout)
        except OSError as exc:  # requests connection errors and timeouts
            last_failure = str(exc) or exc.__class__.__name__
            continue
        if response.status_code in _RETRY_STATUS_CODES:
            last_failure = f"HTTP {response.status_code}"
            continue
        response.raise_for_status()
        return response
    raise OverpassError(
        f"Overpass request to {url} failed after {_ATTEMPTS} attempts "
        f"(last failure: {last_failure})"
    )
