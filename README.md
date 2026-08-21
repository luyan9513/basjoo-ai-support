# Basjoo

[![Docker](https://img.shields.io/badge/Docker-2496ED?logo=docker&logoColor=white)](https://www.docker.com/)
[![FastAPI](https://img.shields.io/badge/FastAPI-009688?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)
[![Next.js](https://img.shields.io/badge/Next.js-000000?logo=next.js&logoColor=white)](https://nextjs.org/)
[![Python](https://img.shields.io/badge/Python-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![TypeScript](https://img.shields.io/badge/TypeScript-3178C6?logo=typescript&logoColor=white)](https://www.typescriptlang.org/)
[![Redis](https://img.shields.io/badge/Redis-DC382D?logo=redis&logoColor=white)](https://redis.io/)
[![Qdrant](https://img.shields.io/badge/Qdrant-Vector_Search-blue)](https://qdrant.tech/)
[![Scrapling](https://img.shields.io/badge/Scrapling-Web_Crawling-green)](https://github.com/D4Vinci/Scrapling)

English | [简体中文](README.zh-CN.md)

Basjoo is an AI customer-support platform with three main parts:

- a **FastAPI backend** for agent configuration, chat, indexing, auth, and scheduling
- a **Next.js admin/dashboard frontend** in `frontend-nextjs/`
- an **embeddable chat widget** in `widget/` that talks to the backend over HTTP and SSE

The stack uses **SQLite** for application data, **Redis** for rate limiting, **Qdrant** for vector search and document indexing, a **Scrapling microservice** for web content fetching, and **nginx** for Docker-based reverse proxying. PostgreSQL/pgvector is available only through the opt-in `experimental-db` profile; the backend is not wired to it and no PostgreSQL driver is installed.

## Suggested environment

Basjoo runs as a set of Docker containers. All LLM inference and embedding calls are made to external APIs (OpenAI, DeepSeek, Anthropic, Gemini, Jina, SiliconFlow), so **no GPU is required**. The figures below are practical starting points, not benchmarked production minimums.

| | Starting point | Comfortable local setup |
|---|---|---|
| CPU | 2 vCPU | 2–4 vCPU |
| RAM | 4 GB | 8 GB |
| Disk | 20 GB | 50 GB |
| OS | Ubuntu 22.04+ / Debian 11+ | Ubuntu 22.04+ / Debian 12+ |
| Docker | 20.10+ | latest |

## Automatic deployment

For a blank Ubuntu or Debian server, run:

```bash
curl -fsSL https://raw.githubusercontent.com/luyan9513/basjoo-ai-support/main/install-deploy.sh | \
  sudo env BASJOO_REPO_URL=https://github.com/luyan9513/basjoo-ai-support BASJOO_BRANCH=main sh
```

If you already have this repository checked out locally, you can also run:

```bash
sudo sh install-deploy.sh
```

After deployment completes, the script prints a prominent summary with the admin dashboard URL. On local desktop environments (with `DISPLAY` or `WAYLAND_DISPLAY` set), it may automatically open the URL in your browser. On headless servers, copy the printed link into a browser.

The first registered admin becomes the workspace super administrator, who can create and manage multiple isolated AI agents within the same workspace.

## Repository structure

- `backend/` — FastAPI app, data models, chat APIs, auth, ingestion, indexing, tests
- `frontend-nextjs/` — active admin/dashboard UI
- `widget/` — embeddable chat widget bundle
- `scrapling-service/` — standalone microservice for web content fetching (curl_cffi + readability)
- `nginx/` — Docker nginx config
- Qdrant vector database service configuration
- `docker-compose.yml` — dev/prod orchestration

## Core features

- Configurable AI agents with multiple provider settings
- Independent Embedding API selection for knowledge retrieval: Jina, SiliconFlow, or a custom OpenAI-compatible endpoint
- URL ingestion and file knowledge management
- Self-KB retrieval (Qdrant-backed) and document indexing via KB pipeline
- Streaming chat responses over Server-Sent Events
- Embeddable website widget with session persistence
- Widget copy auto-translation by visitor locale
- Per-agent widget domain whitelist for public chat embeds
- Offline agent fallback replies and admin-side error alerts
- Admin authentication and dashboard management flows
- Persistent agent-runtime foundation for runs, ordered steps, sanitized tool-call records, approval requests, and workspace-scoped admin inspection/cancellation
- Dockerized development and production-style deployment paths

The runtime foundation does **not** yet make Basjoo a complete task agent. Public chat still uses the existing RAG response path; model-driven tool selection, the order/policy/ticket tool loop, approval decisions/resume, and end-to-end tracing are planned follow-up work.

## Feature walkthrough

### Admin dashboard overview

The admin dashboard is the operational center for configuring agents, reviewing knowledge coverage, and accessing the major management modules.

![English admin dashboard screenshot](resource/screenshots/admin/en-US/dashboard.png)

### Playground and AI configuration

The Playground lets admins test replies, inspect retrieval behavior, and adjust model/provider settings from the same workflow.

![English playground screenshot](resource/screenshots/admin/en-US/playground.png)

### Website knowledge management

The Websites page handles URL ingestion, crawling, auto-fetch settings, and retraining/index-refresh workflows for web content.

![English website management screenshot](resource/screenshots/admin/en-US/websites.png)

### File knowledge management

The File Upload page accepts TXT, Markdown, HTML, PDF, DOCX, and XLSX files as knowledge sources for AI retrieval.

![English file upload screenshot](resource/screenshots/admin/en-US/files.png)

### User management

Manage admin accounts with role-based access control — Super Admin, Admin, and Support roles.

![English user management screenshot](resource/screenshots/admin/en-US/users.png)

### Session operations

The Sessions page shows live conversations, supports human takeover, and gives operators a single place to monitor visitor activity.

![English sessions screenshot](resource/screenshots/admin/en-US/sessions.png)

### Agent settings and widget appearance

Agent Settings covers language/theme preferences, widget appearance, embed behavior, and other operational controls.

![English agent settings screenshot](resource/screenshots/admin/en-US/system-settings.png)

### Embedded widget experience

The widget provides the visitor-facing chat window with persisted sessions, multilingual copy, streaming responses, and knowledge-assisted replies.

![English widget screenshot](resource/screenshots/widget/en-US/widget-window.png)

## Tech stack

### Backend

- FastAPI
- SQLAlchemy async + SQLite
- Redis (rate limiting, caching)
- Qdrant client/API (dense vector search, document indexing, and tenant/KB payload filtering)
- PostgreSQL/pgvector Compose service (opt-in `experimental-db` profile; not used by the backend)
- Scrapling microservice (curl_cffi + readability-lxml web content extraction)
- APScheduler
- Provider SDKs for OpenAI-compatible APIs, Anthropic, and Google Gemini

### Frontend

- Next.js 15.5.21
- React 19.2.8
- TypeScript
- i18next

### Widget

- TypeScript
- esbuild
- Browser-native fetch + SSE handling

## Manual deployment

### Option 1: Docker Compose

Development stack:

```bash
docker compose --profile dev up -d
```

Production-style stack:

```bash
docker compose --profile prod up -d
```

Useful Docker commands:

```bash
docker compose logs -f backend-dev frontend-dev nginx
docker compose --profile dev up -d --build backend-dev frontend-dev
bash scripts/prod_stability_check.sh
```

Default dev ports:

- Frontend: `http://localhost:3000`
- Backend API: `http://localhost:8000`
- Qdrant: `http://localhost:6333`
- PostgreSQL Compose service: `127.0.0.1:5432` (only with `experimental-db`; not used by the backend)
- Redis: `127.0.0.1:6379`

The dev frontend and backend ports are bound as `3000:3000` and `8000:8000`, so they are reachable from other devices that can access the host.

### Option 2: Run services locally

#### Backend

```bash
cd backend
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
python3 main.py
```

Backend health check:

```bash
curl http://localhost:8000/health
curl http://localhost:8000/ready
```

#### Frontend

```bash
cd frontend-nextjs
npm ci
npm run dev
```

#### Widget

```bash
cd widget
npm ci
npm run dev
```

## Common development commands

### Frontend (`frontend-nextjs/`)

```bash
npm ci
npm run dev
npm run build
npm run start        # production build locally
npm run lint
npm run typecheck
npm run test         # vitest
```

### Widget (`widget/`)

```bash
npm ci
npm run dev          # dev bundle + example server
npm run build        # full build (typecheck + dev + prod bundles)
npm run build:dev    # unminified ESM bundle (dist/basjoo-widget.js)
npm run build:prod   # minified IIFE bundle (dist/basjoo-widget.min.js)
npm run typecheck
npm run test         # vitest
```

### Backend (`backend/`)

```bash
pip install -r requirements.txt
python3 main.py
pytest
pytest tests/test_api.py
pytest tests/test_api.py::test_name
```

### Root-level E2E tests

```bash
npm run test:e2e        # smoke tests (dev environment)
npm run test:e2e:all    # all Playwright test projects
npm run test:e2e:prod   # production-like E2E tests
npm run test:e2e:widget # widget cross-origin embed tests
npm run sync-widget     # sync widget bundle to backend
```

### Docker Compose watch mode (dev)

```bash
docker compose --profile dev up --watch
```

## Environment and configuration

The backend reads settings from environment variables and `.env` via `pydantic-settings`.

Important runtime settings used in the current codebase include:

- `DATABASE_URL`
- `REDIS_URL`
- `QDRANT_URL`
- `SECRET_KEY`
- `SECRET_KEY_FILE`
- `DEFAULT_AGENT_ID`
- `JINA_API_KEY`
- `DEEPSEEK_API_KEY`
- `ALLOWED_ORIGINS`
- `ALLOWED_METHODS`
- `ALLOWED_HEADERS`
- `RATE_LIMIT_PER_MINUTE`
- `RATE_LIMIT_BURST_SIZE`
- `LOG_LEVEL`
- `SERVER_DOMAIN`
- `ENCRYPTION_KEY` (optional; auto-generated and persisted if missing)
- `ENCRYPTION_KEY_FILE` (default `/app/data/.encryption_key`)
- `REQUIRE_SECRET_KEY` (set `true` in production to reject insecure secret keys)

Notes:

- If `SECRET_KEY` is missing or insecure, the backend generates one and persists it to `SECRET_KEY_FILE`.
- `DEFAULT_AGENT_ID` can be used to restore or pin a known widget agent ID during migrations; see the deployment section below for the preservation workflow.
- If `ENCRYPTION_KEY` is not set, the backend auto-generates a Fernet key and persists it to `ENCRYPTION_KEY_FILE`; stored provider API keys are encrypted with this key.
- `cors_allow_null_origin` (boolean, default `false`) controls whether `Origin: null` (e.g., `file://` widget preview) receives wildcard CORS headers. Off by default for security.
- `SERVER_DOMAIN` is consumed by the nginx service in the production compose profile to enforce a canonical host and block direct IP/other-host access.
- The dev compose profile sets permissive CORS and local API URLs by default.
- The production compose profile expects mounted persistent backend data under `/app/data`.

## Architecture overview

### Backend

`backend/main.py` builds the FastAPI app and wires together:

- auth routes under `/api/admin`
- v1 APIs under `/api/v1` (chat, agent config, sessions, quotas, task status)
- the main legacy/compatibility v1 routes in `backend/api/v1/endpoints.py`, tenant-scoped KB document routes in `kb_document_endpoints.py`, and workspace-scoped runtime admin routes in `agent_run_endpoints.py`
- public v1 routes: `/api/v1/chat`, `/api/v1/chat/stream`, `/api/v1/contexts`, `/api/v1/config:public`
- CORS middleware with a shared `apply_cors_headers()` helper for early responses (rate limit 429, body size 413)
- i18n middleware
- rate limiting middleware
- Redis and scheduler startup in non-test mode
- static routes for widget assets like `/sdk.js`
- a 10 MiB default body guard for non-upload routes; upload routes allow up to five 20 MiB files plus multipart overhead at the FastAPI layer

The main backend domains are:

- **Agent config**: provider/model/system-prompt/widget settings
- **Knowledge sources**: URLs and uploaded files, with SSRF protection via `backend/services/url_safety.py`
- **Indexing**: chunking content and storing in per-tenant Qdrant collections for data isolation
- **Chat**: session creation, streaming replies, source citations, quota checks
- **Agent runtime foundation**: persistent runs, ordered steps, sanitized tool-call/approval records, explicit state transitions, workspace/membership authorization, and admin inspection/cancellation
- **Admin auth**: dashboard login and registration
- **Scheduling**: URL fetch scheduler, history cleanup, session auto-close (30-min inactivity timeout)

The main persistent entities in `backend/models.py` are:

- `Workspace`
- `Agent`
- `URLSource`
- `KnowledgeFile`
- `ChatSession`
- `ChatMessage`
- `WorkspaceQuota`
- `AgentMember`
- `IndexJob`
- `AdminUser`
- `Tenant`
- `KnowledgeBase`
- `KbDocument`
- `KbChunk`
- `AgentRun`
- `AgentStep`
- `ToolCall`
- `ApprovalRequest`

### Retrieval and provider layer

The retrieval/indexing pipeline spans:

- `backend/api/v1/endpoints.py` (legacy/compatibility URL and index routes)
- `backend/api/v1/kb_document_endpoints.py` (tenant-scoped document routes)
- `backend/services/kb_document_processor.py`
- `backend/services/kb_retrieval_service.py`
- `backend/services/kb_service.py`
- `backend/services/qdrant_service.py`
- `backend/services/scraper.py`
- `backend/services/crawler.py`

Agent runtime persistence and transition rules live in `backend/services/agent_run_service.py`; the corresponding admin router is `backend/api/v1/agent_run_endpoints.py`. Public visitor run endpoints are intentionally absent until signed visitor identity is implemented.

The LLM abstraction is in `backend/services/llm_service.py`. Provider selection is driven by `Agent.provider_type`. The current code supports OpenAI-compatible providers plus dedicated paths for OpenAI Native and Google.

Embedding settings are independent from the chat model provider. Admins can choose Jina, SiliconFlow, or a custom OpenAI-compatible endpoint for knowledge-base indexing/retrieval; the UI only requires the configuration for the selected provider. SiliconFlow can use a dedicated SiliconFlow Embedding API key, with legacy fallback to the main SiliconFlow AI key when the AI provider is also SiliconFlow.

### Frontend

The active UI is the Next.js app in `frontend-nextjs/`.

- App Router routes live under `frontend-nextjs/app/`
- most screen logic lives in `frontend-nextjs/src/views/`
- shared components live in `frontend-nextjs/src/components/`
- admin auth state is stored in `frontend-nextjs/src/context/AuthContext.tsx`
- API calls and SSE parsing are centralized in `frontend-nextjs/src/services/api.ts`

### Widget

`widget/src/BasjooWidget.tsx` is a self-contained embeddable widget that:

- auto-detects `apiBase` from the script source URL, infers from dev port 3000 → backend 8000, or falls back to `window.location.origin`
- fetches `/api/v1/config:public` on init to resolve `default_agent_id`, widget title/color, and welcome message
- stores visitor/session IDs in `localStorage`
- streams chat replies from `/api/v1/chat/stream` via SSE with a 90-second read timeout and one automatic retry on network errors
- polls `/api/v1/chat/messages?role=assistant` at 3-second intervals during human takeover scenarios
- relies on server-side widget origin whitelist checks when configured

The backend serves widget-related assets directly, including `/sdk.js`.

### Security model

- **SSRF protection**: `backend/services/url_safety.py` validates all user-provided URLs. It blocks `localhost`, direct IP literals, URLs with embedded credentials, and hostnames that resolve to private/special-use IPs (loopback, RFC1918, link-local, cloud metadata). DNS resolution results are cached (512-entry LRU) to avoid repeated lookups during crawls.
- **Widget origin whitelist**: Public chat routes enforce a per-agent origin whitelist configured in the admin dashboard. Admin users bypass the whitelist for testing.
- **CORS policy**: Early responses (rate limit 429, body size 413) apply CORS headers through a shared helper in `backend/middleware/rate_limit.py`. `Origin: null` only receives wildcard CORS when `cors_allow_null_origin` is explicitly enabled. Requests without an `Origin` header do not receive CORS headers.
- **Secret persistence**: `SECRET_KEY`, `DEFAULT_AGENT_ID`, and `ENCRYPTION_KEY` are auto-generated and persisted on first boot if not provided via environment variables, ensuring stable widget embed behavior and encrypted API key storage across redeployments.
- **Task concurrency**: A shared `TaskLock` service prevents conflicting operations (e.g., rebuild blocks fetch, fetch blocks rebuild) on the same agent.

## Testing

Backend tests are under `backend/tests/`.

Key testing behavior from `backend/tests/conftest.py`:

- sets `BASJOO_TEST_MODE=1`
- uses isolated SQLite databases under `backend/.pytest_dbs/`
- monkeypatches LLM integrations for many tests
- falls back between Docker hostnames and localhost for Redis where needed

Run all tests:

```bash
cd backend
pytest
```

Run a file:

```bash
pytest tests/test_api.py
```

Run a single test:

```bash
pytest tests/test_api.py::test_name
```

Run the agent-runtime foundation tests:

```bash
pytest -q \
  tests/test_agent_run_service.py \
  tests/test_agent_run_endpoints.py \
  tests/test_agent_run_migration.py
```

## Deployment notes

- `docker-compose.yml` is the main orchestration entrypoint.
- `install-deploy.sh` is the one-command production installer/deployer for Ubuntu and Debian. It can auto-install Docker/Compose and clone or update the repo. Destructive reset/clean and swap changes are disabled unless their explicit opt-in environment variables are set.
- nginx and the backend upload path both allow up to 105 MiB request bodies; ordinary non-upload backend requests remain limited to 10 MiB. The application counts actual streamed bytes instead of trusting only `Content-Length`.
- Optional HTTPS is enabled only when readable certificate and key files exist in `./ssl`.
- When certificates are present, nginx serves HTTPS on port 443 and redirects HTTP requests on port 80 to HTTPS automatically.
- `SERVER_DOMAIN` can be set for the nginx service to enforce a canonical hostname. When set, nginx serves only that host, rejects direct IP or unexpected Host access with nginx 444, and keeps `/health` available for liveness probes. Use `/ready` for dependency readiness.
- If `SERVER_DOMAIN` is not set, nginx keeps accepting requests by the incoming host as before.
- Backend responses that bypass standard middleware should still apply CORS headers so embedded widget requests do not fail cross-origin.
- The backend persists the default widget agent ID to `/app/data/.agent_id`. As long as the backend data volume is preserved, existing widget embed codes keep working after redeployments.
- If you know an older widget agent ID that must keep working, set `DEFAULT_AGENT_ID=agt_xxxxxxxxxxxx` before first boot of the new deployment.
- Avoid `docker compose down -v` or deleting the backend data volume unless you are intentionally rotating widget/embed identity.
- The one-command installer preserves Docker named volumes. Destructive repository reset/clean requires explicit opt-in and should be reviewed before use.

### Preserving existing widget embeds across redeployments

Recommended production workflow:

1. Preserve the backend data volume mounted at `/app/data`.
2. Redeploy with `docker compose --profile prod up -d --build`.
3. If you are migrating to a new server and know the old widget `agentId`, set `DEFAULT_AGENT_ID` before starting the backend.
4. Back up at least `/app/data/basjoo.db` and `/app/data/.agent_id`.

Example `.env` snippet for migration:

```bash
SECRET_KEY=
DEFAULT_AGENT_ID=agt_123456789abc
```

If the old data volume is lost and the old `agentId` is unknown, old widget embeds cannot be recovered automatically because the embed code references the previous agent ID directly.

## API surface at a glance

Examples of backend endpoints present in the codebase:

- `/health`
- `/api/admin/login`
- `/api/admin/register`
- `/api/v1/chat`
- `/api/v1/chat/stream`
- `/api/v1/agent:default`
- `/api/v1/urls:create`
- `/api/v1/urls:list`
- `/api/v1/urls:refetch`
- `/api/v1/index:rebuild`
- `/api/v1/index:status`
- `/api/v1/admin/agent-runs`
- `/api/v1/admin/agent-runs/{run_id}`
- `/api/v1/admin/agent-runs/{run_id}/cancel`
- `/api/v1/admin/approval-requests`

## Acknowledgments

Basjoo is built on top of these amazing open-source projects:

- **[Qdrant](https://qdrant.tech/)** — High-performance vector similarity search engine. Powers Basjoo's self-developed multi-tenant knowledge base.
- **[Scrapling](https://github.com/D4Vinci/Scrapling)** — Stealthy web scraping with TLS fingerprint impersonation (curl_cffi). Powers Basjoo's URL content extraction microservice.
- **[FastAPI](https://github.com/tiangolo/fastapi)** — The web framework powering Basjoo's backend APIs.
- **[Next.js](https://github.com/vercel/next.js)** — The React framework powering Basjoo's admin dashboard.

## Current status

This README reflects the repository as it exists now. If you change deployment flows, provider support, or package scripts, update this file alongside the code.
