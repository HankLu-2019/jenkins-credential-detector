# Jenkins Log Sentinel

A periodic credential leak detector for Jenkins build logs. Scans build logs stored on the filesystem using a three-layer detection funnel (regex → TruffleHog → local LLM), stores findings in PostgreSQL, and surfaces them in a web dashboard with build provenance and owner notifications.

## Why

Jenkins build logs routinely contain credentials that slipped through — passwords in environment variable dumps, API keys echoed by `curl` commands, tokens in stack traces. Unlike source-code scanners, these leaks exist only in log files and are invisible to tools like `git-secrets` or `gitleaks`.

This project fills that gap with a self-hosted, privacy-first scanner that:

- Never sends log data to external APIs (local LLM via Ollama)
- Tracks _who_ triggered the build (Gerrit change owner, manual user, upstream pipeline)
- Lets developers add exemptions so false positives are suppressed on future scans
- Requires no changes to Jenkins itself — read-only filesystem access only

## Architecture

```
/home/jobs/                         Jenkins filesystem (read-only mount)
     │
     ▼
 Discovery                          Walks job/build directories, skips running builds
     │
     ▼
 Provenance parser                  Extracts trigger info from build.xml (no API)
     │                              GERRIT → change owner email
     │                              UPSTREAM → walks chain to originating build
     │                              TIMER / MANUAL → user or fallback channel
     ▼
┌─────────────────────────────────────────────────┐
│  Detection funnel                               │
│                                                 │
│  Stage 1  Regex pre-filter                      │
│           Plaintext patterns (AWS, GitHub,      │
│           GitLab, JWT, passwords, keys, DBs…)  │
│           Base64 pass (Authorization: Basic,    │
│           docker auth, bare b64 near keywords)  │
│                                                 │
│  Stage 2  TruffleHog (optional)                 │
│           Subprocess call, 800+ detector types  │
│           with live credential verification     │
│                                                 │
│  Stage 3  Local LLM (Ollama)                    │
│           Candidates sent with ±5 line context  │
│           Decoded values shown, not raw base64  │
│           Returns: is_credential, type,         │
│           severity, confidence, explanation     │
└─────────────────────────────────────────────────┘
     │
     ▼
 Exemption check                    Skip if matching exemption in DB
     │                              Keyed by: instance, job pattern, type, value hash
     ▼
 PostgreSQL                         findings, builds, exemptions, notifications
     │
     ├──▶  FastAPI backend          REST API for dashboard and exemption management
     │
     ├──▶  Vue 3 dashboard          Findings table, build detail, exemption CRUD
     │
     └──▶  Apprise notifications    Email / Slack / Teams / webhook to build owner
```

## Detection capabilities

| Category            | Examples                                  |
| ------------------- | ----------------------------------------- |
| AWS                 | Access key (`AKIA…`), secret key          |
| GitHub / GitLab     | `ghp_…`, `glpat-…` tokens                 |
| Generic credentials | Password/secret/token assignments         |
| Database URLs       | `postgresql://user:pass@host/db`          |
| Private keys        | PEM RSA/EC/OpenSSH private keys           |
| HTTP Basic Auth     | `Authorization: Basic <base64>` → decoded |
| Docker auth         | `"auth": "<base64>"` in config.json       |
| JWT tokens          | Three-part `eyJ…` tokens                  |
| Google / Slack      | API keys, `xox…` tokens                   |
| Bearer tokens       | `Authorization: Bearer <token>`           |

## Trigger type attribution

Build provenance is read from `build.xml` on disk — no Jenkins REST API required.

| Trigger           | Notification target                                            |
| ----------------- | -------------------------------------------------------------- |
| Gerrit            | Change owner email                                             |
| Manual            | Jenkins user who triggered the build                           |
| Upstream pipeline | Walks the upstream chain to find the originating human trigger |
| Timer / scheduled | Configured `fallback_recipient` (team channel)                 |

## Quickstart

### Prerequisites

- Docker and Docker Compose
- SSH access to the Jenkins jobs directory (or a local path)
- (Optional) [TruffleHog v3](https://github.com/trufflesecurity/trufflehog) installed for Stage 2

### 1. Configure

```bash
cp config.example.yml config.yml
cp .env.example .env
```

Edit `config.yml`:

```yaml
database_url: "postgresql://sentinel:changeme@postgres:5432/sentinel"

jenkins_instances:
  - name: "jenkins-main"
    jobs_path: "/mnt/jenkins-main/jobs"

ollama:
  model: "qwen2.5-coder:7b" # pulled automatically on first start

notifications:
  channels:
    - "mailto://user:pass@smtp.example.com?to=security@example.com"
    - "slack://tokenA/tokenB/tokenC"
  fallback_recipient: "security-team@example.com"
  min_severity: "HIGH"
```

Edit `docker-compose.yml` to mount your Jenkins jobs directory:

```yaml
scanner:
  volumes:
    - /path/to/your/jenkins/jobs:/mnt/jenkins-main/jobs:ro
```

### 2. Start

```bash
docker compose up -d
```

This will:

1. Start PostgreSQL and run DB migrations
2. Pull the Ollama model (first start takes a few minutes)
3. Run an initial log scan
4. Start the API on `localhost:8000` and dashboard on `localhost:3000`

### 3. View findings

Open `http://localhost:3000` in your browser.

### 4. Schedule daily scans

The scanner container loops with a 24-hour sleep. To trigger a manual scan:

```bash
docker compose exec scanner uv run sentinel-scan run
```

To backfill all historical builds:

```bash
docker compose exec scanner uv run sentinel-scan backfill
```

## Running without Docker

```bash
# Install dependencies
uv sync

# Run migrations (requires PostgreSQL)
DATABASE_URL=postgresql://... uv run alembic upgrade head

# Start scanner
SENTINEL_CONFIG=config.yml uv run sentinel-scan run

# Start API
SENTINEL_CONFIG=config.yml uv run uvicorn api.main:app --port 8000

# Start frontend dev server
cd frontend && npm install && npm run dev
```

## Running tests

```bash
uv run python -m pytest tests/ -v
```

## Project structure

```
jenkins-log-sentinel/
  scanner/
    config.py            Pydantic Settings + YAML loader
    discovery.py         Recursive job/build directory walker
    provenance.py        build.xml parser (Gerrit, upstream, timer, manual)
    pipeline.py          5-stage detection funnel orchestrator
    exemptions.py        DB-backed exemption matcher
    main.py              CLI entry point (sentinel-scan run / backfill)
    detectors/
      regex_detector.py  Plaintext + base64/JWT patterns
      trufflehog_detector.py  TruffleHog subprocess wrapper
      llm_detector.py    Ollama async client + prompt

  api/
    main.py              FastAPI app
    routers/             findings, builds, exemptions, stats

  frontend/src/views/
    Dashboard.vue        Summary stats + top jobs by finding count
    Findings.vue         Filterable findings table + inline exemption modal
    BuildDetail.vue      Build provenance + all findings with log context
    Exemptions.vue       Exemption CRUD

  db/
    models.py            SQLAlchemy models (6 tables)
    migrations/          Alembic migrations

  notifications/
    apprise_sender.py    Multi-channel sender + upstream chain resolution

  tests/                 42 unit tests
```

## Database schema

| Table               | Purpose                                                    |
| ------------------- | ---------------------------------------------------------- |
| `jenkins_instances` | Configured Jenkins instances                               |
| `scan_state`        | Last scanned build number per job (incremental scanning)   |
| `builds`            | One record per build with full provenance                  |
| `findings`          | Confirmed credential findings (no plaintext values stored) |
| `exemptions`        | Developer-added suppressions with expiry support           |
| `notifications`     | Outbound notification status tracking                      |

Plaintext secret values are **never stored**. Only a SHA256 hash (for deduplication/exemption matching) and a masked display value (e.g. `AKI***...***PLE`) are persisted.

## Exemptions

When a finding is a false positive (test credential, placeholder, redacted example), a developer can add an exemption from the dashboard. Future scans skip matching findings automatically.

Exemption matching supports:

- `job_name_pattern` — SQL `LIKE` with `%` wildcard, or `null` for all jobs
- `finding_type` — e.g. `GENERIC_PASSWORD`, or `null` for all types
- `content_hash` — SHA256 of the specific value, or `null` to match by type/job only
- `expires_at` — optional expiry date; expired exemptions are ignored

## Configuration reference

| Key                                | Default                  | Description                                       |
| ---------------------------------- | ------------------------ | ------------------------------------------------- |
| `database_url`                     | —                        | PostgreSQL connection string                      |
| `jenkins_instances[].name`         | —                        | Instance identifier                               |
| `jenkins_instances[].jobs_path`    | —                        | Absolute path to jobs directory                   |
| `ollama.base_url`                  | `http://localhost:11434` | Ollama server URL                                 |
| `ollama.model`                     | `qwen2.5-coder:7b`       | Model for LLM classification                      |
| `ollama.timeout_seconds`           | `120`                    | Per-request timeout                               |
| `scan.initial_backfill_days`       | `7`                      | Days back to scan on first run                    |
| `scan.concurrency`                 | `4`                      | Parallel log pipelines                            |
| `scan.max_log_size_bytes`          | `52428800`               | Skip logs larger than this (0 = no limit)         |
| `notifications.channels`           | `[]`                     | [Apprise URLs](https://github.com/caronc/apprise) |
| `notifications.fallback_recipient` | `""`                     | Used for timer-triggered builds                   |
| `notifications.min_severity`       | `HIGH`                   | Minimum severity to notify                        |
| `trufflehog.binary`                | `trufflehog`             | Path to TruffleHog v3 binary                      |

## Privacy

All log processing happens locally. The LLM stage uses Ollama — no data leaves your network. The only external calls are optional TruffleHog credential verification (can be disabled by leaving `trufflehog.binary` empty).

## License

MIT
