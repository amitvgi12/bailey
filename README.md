# bailey

**Portable bridges for AI agents into enterprise APIs. Zero dependencies. JSON everywhere. Safe by default.**

Named after the [Bailey bridge](https://en.wikipedia.org/wiki/Bailey_bridge) — the portable, prefabricated bridge famous for being assembled fast, anywhere, with no special tools. That's the whole idea.

## The problem

AI coding agents (Claude Code, and friends) are brilliant at operating anything with a CLI — and helpless in front of the enterprise tools where your actual work lives. Confluence. Jira. The wikis and trackers behind your corporate VPN.

The usual answers don't survive contact with a locked-down corporate machine:

- **MCP servers** need Node runtimes, network egress, or admin approval you don't have.
- **SDKs** need `pip install` on boxes where PyPI is blocked.
- **Browser automation** is slow, brittle, and terrifying to security teams.

## The pattern

One tiny Python package. **Standard library only** — if a machine has Python 3.9+, bailey runs on it. Copy the folder, set two environment variables, and your agent can read and write enterprise systems through a CLI contract designed for non-humans:

- **JSON on stdout, always.** Agents parse; humans can too.
- **Stable exit codes.** `0` ok · `1` error · `3` auth · `4` not found · `5` version conflict. An agent can branch on `$?` without parsing prose.
- **No interactive prompts, ever.** Everything arrives via args, files, or stdin.
- **Optimistic concurrency.** `update-page --expect-version N` aborts (exit 5) if a human edited the page since the agent last read it. Autonomous writes without overwrite accidents.
- **`--dry-run` on every mutating command.** See the exact payload before anything is sent.

## Install

```bash
pipx install bailey-bridge        # when published to PyPI
# or, the locked-down-machine way — it's stdlib-only, just copy it:
git clone https://github.com/amitvgi12/bailey && cd bailey
python3 -m bailey --version
```

## Configure

```bash
# Confluence Data Center / Server (PAT):
export BAILEY_CONFLUENCE_URL="https://confluence.your-company.com"
export BAILEY_CONFLUENCE_TOKEN="your-personal-access-token"

# Confluence Cloud (email + API token → add EMAIL, auth switches to Basic):
export BAILEY_CONFLUENCE_URL="https://your-site.atlassian.net/wiki"
export BAILEY_CONFLUENCE_EMAIL="you@company.com"
export BAILEY_CONFLUENCE_TOKEN="your-api-token"

# Jira: same convention with BAILEY_JIRA_URL / _TOKEN / _EMAIL

# Self-hosted instance behind a corporate/internal CA? Point bailey at the
# PEM bundle — verification stays ON (there is deliberately no "insecure" flag):
export BAILEY_CA_BUNDLE="/etc/ssl/corp-root-ca.pem"
```

**Self-hosted (Data Center) notes:** set only `URL` + `TOKEN` (PAT → Bearer auth,
per Atlassian's DC docs); do **not** set `EMAIL`. Context-path installs
(`https://host/confluence`) work — bailey appends `/rest/api` to whatever base
you give. Corporate proxies are honored via standard `HTTPS_PROXY`/`HTTP_PROXY`
env vars. Pre-7.9 Confluence *Server* has no PATs: set `EMAIL` to a username and
`TOKEN` to the password to force Basic auth.

Tokens live in environment variables only — never in arguments (visible in `ps`/shell history) and never in files bailey writes.

## Use

```bash
# Read a page as plain text (agent-friendly)
bailey confluence get-page --id 123456 --text

# Search with CQL
bailey confluence search --cql 'space = OPS and title ~ "runbook"'

# Create a page from stdin
echo "<p>Deploy checklist v2</p>" | bailey confluence create-page \
  --space OPS --title "Deploy Checklist" --file -

# Update safely: abort if someone edited since version 7
bailey confluence update-page --id 123456 --file new-body.xml \
  --expect-version 7 --message "automated update" --dry-run

# Jira
bailey jira get-issue --key OPS-42
bailey jira search --jql 'project = OPS and status = "In Progress"'
bailey jira comment --key OPS-42 --body "Deployed to UAT." --dry-run
```

## Use with AI agents

`skills/bailey-confluence/` ships a ready-to-install **Claude Agent Skill** that teaches Claude Code when and how to drive bailey — including the safety rules (always `--expect-version`, `--dry-run` first, treat page content as untrusted data).

```bash
cp -r skills/bailey-confluence ~/.claude/skills/
```

## Why not just curl?

Fair question — it's all REST underneath, and an agent *can* call the API raw. It just does it badly, expensively, and dangerously:

- **Dangerously.** Confluence's update API makes you fetch the version, increment it, and resend the body — and accepts whatever you send. Agent reads v7, a human edits to v8, agent writes v9: the human's edit is silently gone. Raw curl has no defense. `--expect-version` refuses that write (exit 5). Tokens improvised into curl commands also land in shell history and logs; bailey only reads them from env.
- **Expensively.** Every raw session, the agent re-derives endpoints, cloud-vs-DC auth, the `/wiki` quirk, storage-format payloads, and 429 handling — hundreds of tokens to rebuild a fragile incantation, every time. With bailey it's one short, identical command; the API fiddliness is paid for once, in the tool.
- **Unreliably.** Parsing raw output means improvised error recovery. JSON-always plus stable exit codes (0/1/3/4/5) means the agent *branches* instead of *interprets*: exit 5 → re-read and retry once; exit 3 → stop and ask a human.

Agents don't strictly need `kubectl` either — Kubernetes is just REST too. Nobody sane lets an agent curl the API server. Good CLIs are how APIs become safe and cheap to operate; agents deserve one built for them.

(If you're a human scripting Confluence on an unrestricted machine, curl or the existing Atlassian libraries are genuinely fine — bailey's edge there is only the zero-dependency install. The full value appears when the operator is an **agent** on a **locked-down box**.)

## Design principles

1. **Zero dependencies is a feature, not a constraint.** Every dependency is a procurement conversation on a corporate machine.
2. **The agent is the user.** Output, errors, and exit codes are the API.
3. **Reads are free, writes are guarded.** Version checks and dry-runs make autonomous operation boring — the good kind of boring.
4. **Adapters, not a tool.** Confluence and Jira today; the core (`_http.py`) is ~150 lines and any REST API is an afternoon away.

## Security notes

- Page and issue content fetched by bailey is **untrusted input** to your agent. Instructions embedded in a wiki page are data, not commands — the bundled skill says so explicitly.
- Scope tokens to the narrowest spaces/projects your workflow needs.
- bailey never logs, stores, or echoes credentials.

## Roadmap

- [ ] PyPI release (`bailey-bridge`)
- [ ] Attachment upload/download
- [ ] Adapter: ServiceNow
- [ ] Adapter: generic OpenAPI-described REST endpoints
- [ ] `bailey doctor` — connectivity/auth self-check

## Status & disclaimer

v0.1.0 — young, tested against the public Atlassian REST API spec with a full unit suite; validate against your own instance before trusting it with production wikis. Personal project; not affiliated with or endorsed by Atlassian or any employer.

## License

MIT © 2026 Amit Kumar