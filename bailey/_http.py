"""bailey._http — stdlib-only HTTP with retries, backoff, and typed errors.

Design rules:
- Zero third-party dependencies. urllib is enough.
- Every failure maps to a typed error with a stable shell exit code,
  so AI agents (and shell scripts) can branch on outcomes reliably.
- Retries only on transient statuses, with exponential backoff and
  respect for Retry-After.
"""
from __future__ import annotations

import base64
import json
import os
import ssl
import time
import urllib.error
import urllib.parse
import urllib.request

USER_AGENT = "bailey/0.1 (zero-dependency agent bridge)"
RETRY_STATUSES = {429, 502, 503, 504}


def _ssl_context() -> ssl.SSLContext:
    """System trust store by default; BAILEY_CA_BUNDLE adds a corporate CA.

    Self-hosted Confluence/Jira commonly sits behind an internal CA. Point
    BAILEY_CA_BUNDLE at the PEM file and verification keeps working —
    bailey never offers an 'ignore certificates' switch on purpose.
    """
    cafile = os.environ.get("BAILEY_CA_BUNDLE", "").strip()
    if cafile:
        if not os.path.isfile(cafile):
            raise AuthError(f"BAILEY_CA_BUNDLE points to a missing file: {cafile}")
        return ssl.create_default_context(cafile=cafile)
    return ssl.create_default_context()


class BridgeError(Exception):
    """Base error. `exit_code` is the shell exit status agents can rely on."""

    exit_code = 1


class AuthError(BridgeError):
    """401/403 or missing credentials."""

    exit_code = 3


class NotFoundError(BridgeError):
    """404 — the resource does not exist (or you can't see it)."""

    exit_code = 4


class ConflictError(BridgeError):
    """409 or an optimistic-concurrency version mismatch."""

    exit_code = 5


class ApiError(BridgeError):
    """Any other non-2xx response."""

    def __init__(self, status: int, message: str, body: str = ""):
        super().__init__(f"HTTP {status}: {message}")
        self.status = status
        self.body = body


def _classify(status: int, message: str, body: str) -> BridgeError:
    if status in (401, 403):
        return AuthError(f"HTTP {status}: {message} — check your token/env vars")
    if status == 404:
        return NotFoundError(f"HTTP 404: {message}")
    if status == 409:
        return ConflictError(f"HTTP 409: {message}")
    return ApiError(status, message, body)


def request(
    method: str,
    url: str,
    *,
    bearer: str | None = None,
    basic: tuple[str, str] | None = None,
    params: dict | None = None,
    json_body: dict | None = None,
    timeout: int = 30,
    max_retries: int = 3,
):
    """Perform an HTTP request. Returns parsed JSON (dict/list) or raw text.

    Raises a typed BridgeError subclass on failure.
    """
    if params:
        sep = "&" if "?" in url else "?"
        url = url + sep + urllib.parse.urlencode(params)

    headers = {"Accept": "application/json", "User-Agent": USER_AGENT}
    data = None
    if json_body is not None:
        data = json.dumps(json_body).encode("utf-8")
        headers["Content-Type"] = "application/json"

    if bearer:
        headers["Authorization"] = "Bearer " + bearer
    elif basic:
        raw = f"{basic[0]}:{basic[1]}".encode("utf-8")
        headers["Authorization"] = "Basic " + base64.b64encode(raw).decode("ascii")

    context = _ssl_context() if url.lower().startswith("https") else None
    last_error: BridgeError | None = None
    for attempt in range(max_retries + 1):
        req = urllib.request.Request(url, data=data, headers=headers, method=method)
        try:
            with urllib.request.urlopen(req, timeout=timeout, context=context) as resp:
                text = resp.read().decode("utf-8", errors="replace")
                if not text:
                    return {}
                try:
                    return json.loads(text)
                except json.JSONDecodeError:
                    return text
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", errors="replace")
            message = _extract_message(body) or e.reason or "request failed"
            if e.code in RETRY_STATUSES and attempt < max_retries:
                delay = _retry_delay(e.headers.get("Retry-After"), attempt)
                time.sleep(delay)
                last_error = _classify(e.code, message, body)
                continue
            raise _classify(e.code, message, body) from None
        except urllib.error.URLError as e:
            if attempt < max_retries:
                time.sleep(2**attempt)
                last_error = ApiError(0, f"network error: {e.reason}")
                continue
            raise ApiError(0, f"network error: {e.reason}") from None
    raise last_error or ApiError(0, "request failed after retries")


def _retry_delay(retry_after: str | None, attempt: int) -> float:
    if retry_after:
        try:
            return min(float(retry_after), 60.0)
        except ValueError:
            pass
    return float(2**attempt)


def _extract_message(body: str) -> str:
    """Pull a human-readable message out of a JSON error body, if present."""
    try:
        parsed = json.loads(body)
    except (json.JSONDecodeError, TypeError):
        return ""
    if isinstance(parsed, dict):
        for key in ("message", "errorMessage", "error"):
            value = parsed.get(key)
            if isinstance(value, str) and value:
                return value
        msgs = parsed.get("errorMessages")
        if isinstance(msgs, list) and msgs:
            return "; ".join(str(m) for m in msgs)
    return ""
