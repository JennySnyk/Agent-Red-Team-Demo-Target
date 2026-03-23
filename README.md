# SmartPal

A deliberately vulnerable AI assistant for red-teaming demos. SmartPal is a
"productivity platform" backed by an LLM agent with 16 tools.

Use it as a target for [`snyk redteam`](https://docs.snyk.io/developer-tools/snyk-cli/commands/redteam)

---

## Quick Start

### Prerequisites

- **[Docker](https://www.docker.com/products/docker-desktop/)**
- **[Snyk CLI](https://docs.snyk.io/snyk-cli/install-or-update-the-snyk-cli)** — run `snyk auth` once
- **An LLM API key** — bring your own key (BYOK) from any supported provider:

| Provider | Model | Get a Key |
|----------|-------|-----------|
| `google` | `gemini-3.1-flash-lite-preview` | [aistudio.google.com/apikey](https://aistudio.google.com/apikey) |
| `openai` | `gpt-5.4-mini` | [platform.openai.com/api-keys](https://platform.openai.com/api-keys) |
| `anthropic` | `claude-haiku-4-5` | [console.anthropic.com/settings/keys](https://console.anthropic.com/settings/keys) |

### Run a Scan

```bash
make demo-scan API_KEY=<your-key> PROVIDER=google|openai|anthropic
```

That's it. The Makefile builds SmartPal in Docker, starts it, discovers a JWT token,
runs the scan, and tears everything down automatically.

### Options

| Variable | Default | Description |
|----------|---------|-------------|
| `API_KEY` | *(required)* | LLM provider API key |
| `PROVIDER` | *(required)* | `google`, `openai`, or `anthropic` |
| `JSON_OUTPUT` | *(none)* | Save results to a JSON file |
| `PROFILE` | *(none)* | Override scan profile (e.g. `security`) |

### Teardown

The scan tears down automatically. If something goes wrong:

```bash
make demo-down
```

---

## What the Scan Finds

The default config (`redteaming/redteam.yaml`) runs 4 attacks:

| Attack | Strategy | What it targets |
|--------|----------|----------------|
| System Prompt Extraction | `directly_asking` | Internal URLs, DB path, admin override code in the system prompt |
| PII Extraction | `directly_asking` | Cross-user contacts, notes, emails via IDOR |
| Capability Extraction | `directly_asking` | Full tool inventory disclosure |
| Privilege Escalation | `agentic` | Cross-user settings writes (e.g. disabling 2FA) |

Override with `PROFILE=security` (~23 attacks, ~5 min).

---

## Vulnerability Surface

SmartPal ships with seven categories of intentional vulnerabilities. The scanner
authenticates as **Jane** (guest). **Joe** (owner) has the sensitive data.

| # | Category | OWASP | Description |
|---|----------|-------|-------------|
| 1 | **System Prompt Extraction** | LLM07 | Prompt contains internal URLs, DB path, JWT config, admin override code |
| 2 | **PII Extraction (IDOR)** | LLM02 | Every tool accepts `user_id` with no auth check — Jane reads Joe's data |
| 3 | **Indirect Prompt Injection** | LLM01 | Joe's note contains embedded instructions that trigger autonomous exfiltration |
| 4 | **Excessive Agency** | LLM08 | Agent composes and sends emails without confirmation |
| 5 | **Privilege Escalation** | LLM06 | Jane disables Joe's 2FA via `_update_setting` |
| 6 | **Code Execution** | LLM06 | `_execute_python_code` returns mock env dump (fake AWS/JWT keys) |
| 7 | **Multi-Turn Crescendo** | — | Gradual escalation across session turns via `X-SmartPal-Session: auto` |

---


### Seed Data

| User | Role | Key Data |
|------|------|----------|
| **Joe** | owner | Credentials note (DB password, API keys), board meeting notes (financials), Q3 outreach note (injection payload), investor + salary email drafts, 2FA enabled |
| **Jane** | guest | Personal todo note, support email, 2FA enabled |

---

## Security

- **API key** — forwarded via env var; never visible in `docker ps`
- **JWT tokens** — ephemeral; auto-generated per container start, destroyed on teardown
- **Mock secrets** — code execution returns canned fake credentials, never runs real code
- **No persistence** — SQLite in-memory, sessions in-process; nothing survives a restart

## License

[Apache License 2.0](LICENSE)