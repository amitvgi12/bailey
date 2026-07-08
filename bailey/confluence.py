"""bailey.confluence — Confluence adapter (Cloud and Data Center).

Written against Atlassian's public Confluence REST API (`/rest/api/content`).
Auth, per Atlassian's public docs:
- Cloud: email + API token via HTTP Basic.
- Data Center/Server: Personal Access Token via Bearer.

Env vars:
    BAILEY_CONFLUENCE_URL     e.g. https://your-site.atlassian.net/wiki
                              or   https://confluence.your-company.com
    BAILEY_CONFLUENCE_TOKEN   API token (cloud) or PAT (Data Center)
    BAILEY_CONFLUENCE_EMAIL   set ONLY for cloud (switches auth to Basic)
"""
from __future__ import annotations

import os
from html.parser import HTMLParser

from . import _http
from ._http import AuthError, ConflictError

_BLOCK_TAGS = {"p", "div", "br", "li", "tr", "h1", "h2", "h3", "h4", "h5", "h6",
               "table", "ul", "ol", "blockquote", "pre"}


class _TextExtractor(HTMLParser):
    """Minimal storage-format → plain text conversion. Stdlib only."""

    def __init__(self):
        super().__init__()
        self.parts: list[str] = []

    def handle_data(self, data):
        self.parts.append(data)

    def handle_starttag(self, tag, attrs):
        if tag in _BLOCK_TAGS:
            self.parts.append("\n")

    def text(self) -> str:
        raw = "".join(self.parts)
        lines = [ln.strip() for ln in raw.splitlines()]
        return "\n".join(ln for ln in lines if ln)


class Confluence:
    def __init__(self, base_url: str, *, bearer: str | None = None,
                 basic: tuple[str, str] | None = None):
        base = base_url.rstrip("/")
        # Atlassian cloud serves Confluence under /wiki; add it if missing.
        if ".atlassian.net" in base and not base.endswith("/wiki"):
            base += "/wiki"
        self.base = base
        self.api = base + "/rest/api"
        self._auth = {"bearer": bearer, "basic": basic}

    # ---------------------------------------------------------------- auth
    @classmethod
    def from_env(cls, env=None) -> "Confluence":
        env = env if env is not None else os.environ
        url = env.get("BAILEY_CONFLUENCE_URL", "").strip()
        token = env.get("BAILEY_CONFLUENCE_TOKEN", "").strip()
        email = env.get("BAILEY_CONFLUENCE_EMAIL", "").strip()
        if not url:
            raise AuthError("BAILEY_CONFLUENCE_URL is not set")
        if not token:
            raise AuthError("BAILEY_CONFLUENCE_TOKEN is not set")
        if email:  # cloud: Basic email:api-token
            return cls(url, basic=(email, token))
        return cls(url, bearer=token)  # Data Center: Bearer PAT

    def _req(self, method: str, path: str, **kw):
        return _http.request(method, self.api + path, **self._auth, **kw)

    # ---------------------------------------------------------------- read
    def get_page(self, page_id: str, expand: str = "body.storage,version,space"):
        return self._req("GET", f"/content/{page_id}", params={"expand": expand})

    def page_text(self, page_id: str) -> dict:
        page = self.get_page(page_id)
        storage = (page.get("body", {}).get("storage", {}) or {}).get("value", "")
        extractor = _TextExtractor()
        extractor.feed(storage)
        return {
            "id": page.get("id"),
            "title": page.get("title"),
            "version": page.get("version", {}).get("number"),
            "text": extractor.text(),
        }

    def search(self, cql: str, limit: int = 25):
        return self._req("GET", "/content/search",
                         params={"cql": cql, "limit": limit})

    def spaces(self, limit: int = 25):
        return self._req("GET", "/space", params={"limit": limit})

    # --------------------------------------------------------------- write
    def create_page(self, space_key: str, title: str, storage_body: str,
                    parent_id: str | None = None) -> dict:
        payload = {
            "type": "page",
            "title": title,
            "space": {"key": space_key},
            "body": {"storage": {"value": storage_body,
                                 "representation": "storage"}},
        }
        if parent_id:
            payload["ancestors"] = [{"id": parent_id}]
        return self._req("POST", "/content", json_body=payload)

    def update_page(self, page_id: str, *, storage_body: str | None = None,
                    title: str | None = None, expect_version: int | None = None,
                    message: str = "", minor_edit: bool = False,
                    dry_run: bool = False) -> dict:
        """Optimistic-concurrency update.

        Fetches the live version first. If `expect_version` is given and the
        live version differs, raises ConflictError instead of overwriting —
        the safety rail that makes this usable by autonomous agents.
        """
        current = self.get_page(page_id)
        live_version = current.get("version", {}).get("number", 0)
        if expect_version is not None and expect_version != live_version:
            raise ConflictError(
                f"page {page_id}: expected v{expect_version}, live is "
                f"v{live_version} — someone edited it; re-read before writing"
            )
        payload: dict = {
            "type": "page",
            "title": title or current.get("title"),
            "version": {"number": live_version + 1,
                        "minorEdit": minor_edit},
        }
        if message:
            payload["version"]["message"] = message
        if storage_body is not None:
            payload["body"] = {"storage": {"value": storage_body,
                                           "representation": "storage"}}
        else:
            existing = (current.get("body", {}).get("storage", {}) or {})
            payload["body"] = {"storage": {"value": existing.get("value", ""),
                                           "representation": "storage"}}
        if dry_run:
            return {"dry_run": True, "would_send": payload,
                    "live_version": live_version}
        return self._req("PUT", f"/content/{page_id}", json_body=payload)
