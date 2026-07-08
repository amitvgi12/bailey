"""bailey.jira — minimal Jira adapter (Cloud and Data Center).

Written against Atlassian's public Jira REST API v2. Deliberately small:
it exists to prove bailey is a *pattern*, not a single tool. Same auth
convention as the Confluence adapter.

Env vars:
    BAILEY_JIRA_URL      e.g. https://your-site.atlassian.net
    BAILEY_JIRA_TOKEN    API token (cloud) or PAT (Data Center)
    BAILEY_JIRA_EMAIL    set ONLY for cloud (switches auth to Basic)
"""
from __future__ import annotations

import os

from . import _http
from ._http import AuthError


class Jira:
    def __init__(self, base_url: str, *, bearer: str | None = None,
                 basic: tuple[str, str] | None = None):
        self.base = base_url.rstrip("/")
        self.api = self.base + "/rest/api/2"
        self._auth = {"bearer": bearer, "basic": basic}

    @classmethod
    def from_env(cls, env=None) -> "Jira":
        env = env if env is not None else os.environ
        url = env.get("BAILEY_JIRA_URL", "").strip()
        token = env.get("BAILEY_JIRA_TOKEN", "").strip()
        email = env.get("BAILEY_JIRA_EMAIL", "").strip()
        if not url:
            raise AuthError("BAILEY_JIRA_URL is not set")
        if not token:
            raise AuthError("BAILEY_JIRA_TOKEN is not set")
        if email:
            return cls(url, basic=(email, token))
        return cls(url, bearer=token)

    def _req(self, method: str, path: str, **kw):
        return _http.request(method, self.api + path, **self._auth, **kw)

    def get_issue(self, key: str, fields: str = "summary,status,assignee,description"):
        return self._req("GET", f"/issue/{key}", params={"fields": fields})

    def search(self, jql: str, limit: int = 25):
        return self._req("POST", "/search",
                         json_body={"jql": jql, "maxResults": limit,
                                    "fields": ["summary", "status", "assignee"]})

    def add_comment(self, key: str, body: str, dry_run: bool = False):
        if dry_run:
            return {"dry_run": True, "would_send": {"body": body},
                    "issue": key}
        return self._req("POST", f"/issue/{key}/comment",
                         json_body={"body": body})
