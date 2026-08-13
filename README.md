# AI-Powered Creative Ads System

Move from a campaign brief to a reviewable full-funnel creative set without losing control of the output. This Streamlit workspace turns a persona, market, and primary funnel focus into seven validated ad variants, five short-form video concepts, and a Notion review queue. It is built for growth teams and creative operators who want a structured starting point for human review, not automatic ad publishing.

![Creative Ads System workspace](docs/assets/screenshots/creative-ads-dashboard.png)

*Local application shell before a provider-backed run. Creative cards, video status, and Notion records appear after sign-in and provider configuration.*

## The product workflow

1. Enter the target persona, market, and funnel focus.
2. Generate a fixed creative set: seven ads across awareness, mid-funnel, conversion, and Spanish full-funnel coverage, plus five distinct video prompts.
3. Validate the whole payload before any video request is made.
4. Create one review record per ad in Notion, start the five KIE/Runway video jobs, and poll their status from the workspace.
5. Review, tag, annotate, and regenerate individual ads with feedback. A person still approves anything that leaves the tool.

The fixed set makes comparisons deliberate rather than accidental: A–C are English awareness variants on V1–V3; D and E are English mid-funnel variants sharing V4; F is an English conversion variant on V5; G is Spanish full-funnel copy on V4. The validator requires that mapping, five unique prompts, all seven labels, echoed brief inputs, and non-empty copy before downstream work begins.

## What stands out

- **A repeatable creative contract.** Each run produces the same reviewable shape instead of an unbounded collection of suggestions.
- **Copy and motion in one handoff.** The system pairs each ad with a video concept and tracks asynchronous video results against the relevant Notion records.
- **Feedback stays attached to the work.** Reviewers can update tags and notes in Notion, then regenerate a single ad instead of throwing away a complete set.
- **Useful failure boundaries.** Provider responses are parsed as structured data, bounded by input and output limits, and surfaced through generic UI errors.

## Architecture

```mermaid
flowchart LR
  A[Creative operator] --> B[Authenticated Streamlit workspace]
  B --> C[Groq structured copy generation]
  C --> D[Creative-contract validator]
  D --> E[Notion review records]
  D --> F[KIE / Runway video tasks]
  F --> G[Bounded status polling]
  G --> E
  E --> H[Human review and single-ad regeneration]
```

## Tech stack

| Layer | Implementation |
| --- | --- |
| Product UI and orchestration | Streamlit, Python 3.10+ |
| Copy generation | Groq chat completions (`llama-3.3-70b-versatile`) |
| Video generation | KIE API's Runway endpoints, 5-second 720p 9:16 tasks |
| Review surface | Notion database API |
| Contracts and HTTP | Python validation module, `requests` |
| Quality gates | Ruff and pytest; provider calls are mocked in tests |

## Run it locally

You need Python 3.10 or newer plus Groq, KIE, and Notion credentials.

```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
python -m pip install -r requirements.txt
cp .env.example .env
streamlit run app.py
```

Set the required values in `.env` before opening the app:

| Variable | Used for |
| --- | --- |
| `CREATIVE_ADS_ACCESS_TOKEN` | Shared access token for the workspace |
| `GROQ_API_KEY` | Creative-copy generation |
| `KIE_API_KEY` | Video task creation and status checks |
| `NOTION_API_KEY`, `NOTION_DATABASE_ID` | Creating and updating review records |
| `NOTION_VERSION` | Notion API version; the example uses `2022-06-28` |

`NOTION_DATA_SOURCE_ID` is optional when the target is a data source. `KIE_CALLBACK_URL` is optional; when supplied, it should be an operator-controlled HTTPS endpoint.

Create a Notion database with these required properties: `Set ID`, `Persona`, `Market`, `Funnel Stage`, `Ad Label`, `Language`, `Headline`, `Primary Text`, `CTA`, `Video ID`, `Video URL`, `Reused?`, and `Status`. `Tag`, `Iteration`, and `Notes` are supported review fields.

## Engineering decisions and verification

The system treats generated JSON as untrusted. It checks exact top-level keys, the run's set ID and echoed inputs, the A–G/V1–V5 mapping, unique prompts, required text fields, and size limits before persisting work or starting video jobs. Persona and market inputs are capped at 500 and 300 characters; generated fields are capped at 8,000 characters. Video polling waits five seconds between attempts and stops after 60 attempts per task.

Run the local quality gates with:

```bash
python -m pip install -r requirements-dev.txt
python -m ruff check .
python -m pytest
```

The CI matrix runs these gates on Python 3.10 and 3.12. Tests cover the creative contract, safe Streamlit rendering, Notion schema/request behavior, and mocked provider retries and failure paths. They do not call paid services.

## Provider and cost model

A successful set makes at least one Groq request and starts five KIE video tasks. Regenerating an individual ad makes another Groq request; regeneration never begins another full set by itself. Notion API requests support record creation, review updates, and video-status updates.

Prices, quotas, and model availability belong to the providers and can change. Set provider-side spend caps and watch request volume before sharing the workspace with a team. The application does not include a billing ledger, queue, or durable job scheduler.

## Security and current limits

The UI fails closed without `CREATIVE_ADS_ACCESS_TOKEN`; secrets stay server-side. The application escapes provider and Notion text before HTML rendering, bounds Notion pagination, uses a single bounded retry for transient provider failures, and does not automatically publish ads.

This is a controlled single-process workspace, not a multi-tenant campaign platform. It uses a shared secret rather than per-user identity, keeps active work in the Streamlit session, and can experience partial writes across Groq, KIE, and Notion. A production deployment should add SSO and authorization, per-user quotas, validated callback destinations, durable jobs with idempotency, audit logging, and retention controls. Review brand, legal, and platform-policy requirements before publishing any creative.

## Repository map

- `app.py` — authenticated Streamlit workflow, review actions, and video polling.
- `services/llm.py` — Groq prompts and structured-response handling.
- `services/video.py` — KIE/Runway task and status adapter.
- `services/notion.py` — schema-aware Notion persistence and bounded queries.
- `services/validator.py` — creative-set contract and limits.
- `tests/` — deterministic unit and mocked integration tests.

## License

All rights reserved. This repository is provided for portfolio, review, and demonstration purposes; see [LICENSE](LICENSE).
