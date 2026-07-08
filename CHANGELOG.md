# Changelog

## 0.1.0 — 2026-07-05

Initial release.

- `BAILEY_CA_BUNDLE` for self-hosted instances behind corporate CAs (verification always on; no insecure mode by design).

- Zero-dependency core HTTP layer: retries with backoff, Retry-After support,
  typed errors mapped to stable exit codes (0/1/3/4/5).
- Confluence adapter (Cloud + Data Center): get-page (JSON or plain text),
  CQL search, list spaces, create-page, update-page with optimistic
  concurrency (`--expect-version`) and `--dry-run`.
- Jira adapter (minimal): get-issue, JQL search, comment with `--dry-run`.
- Bundled Claude Agent Skill (`skills/bailey-confluence`) with the write
  safety ritual and untrusted-content rules.
- 15-test unit suite; CI across Python 3.9–3.13.
