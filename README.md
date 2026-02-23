# AI-Powered Creative Ads System

A production-ready system that generates complete ad creative sets — copy, targeting, and AI-generated videos — for every stage of the marketing funnel, all managed through a centralized dashboard.

---

## What It Does

Enter a **target persona** and **market**, and the system automatically produces:

- **7 unique ad creatives** (A through G) covering Awareness, Mid-funnel, Conversion, and multi-language variants
- **5 AI-generated videos** (5-second vertical clips, optimized for social media)
- **Full lifecycle management** — tag, annotate, and iterate on every creative from one place

Everything is stored in a Notion database as the single source of truth.

---

## Features

### One-Click Generation
Input your target audience and market, hit Generate, and the system creates an entire ad set — headlines, primary text, CTAs, and videos — in under two minutes.

### Full-Funnel Coverage
Every generation produces ads mapped across the entire funnel:

| Ad | Funnel Stage | Language | Video | Purpose |
|----|-------------|----------|-------|---------|
| A | Awareness | English | V1 | Top-of-funnel hook |
| B | Awareness | English | V2 | Alternative awareness angle |
| C | Awareness | English | V3 | Third awareness variant |
| D | Mid-funnel | English | V4 | Consideration / engagement |
| E | Mid-funnel | English | V4 | Copy variant (same video as D) |
| F | Conversion | English | V5 | Direct response / CTA-heavy |
| G | Full-funnel | Spanish | V4 | Multi-language market variant |

### AI Video Generation
Each creative set includes 5 distinct AI-generated video assets — vertical format (9:16), 720p, 5 seconds — designed for platforms like Instagram Reels, TikTok, and YouTube Shorts.

### Creative Manager
Browse, filter, and manage all your generated creatives:
- **Filter** by set, funnel stage, language, or tag
- **Tag** creatives as Winner, Approved, Testing, Needs Revision, or Draft
- **Annotate** with notes and feedback
- **Preview** videos inline alongside ad copy

### Single-Ad Regeneration
Don't like one ad in a set? Provide specific feedback and regenerate just that creative — the system keeps your feedback context and updates the copy without touching the rest of the set.

### Notion as Source of Truth
All creatives live in a Notion database with full properties: headline, primary text, CTA, funnel stage, language, video URL, tags, iteration count, and notes. Your team can collaborate directly in Notion or through the app.

---

## Live Demo

**[View the app on Streamlit Cloud]()**

> Replace with your Streamlit Cloud URL after deployment.

---

## How It Works

```
1. You enter a persona + market
       |
2. LLM generates 7 ad creatives with copy, CTAs, and video prompts
       |
3. 5 AI videos are generated from the video prompts
       |
4. Everything is saved to your Notion database
       |
5. You review, tag, annotate, and regenerate from the dashboard
```

---

## Getting Started

### Prerequisites
- Python 3.9+
- API keys for: LLM service, Video generation service, and Notion

### Installation

```bash
pip install -r requirements.txt
cp .env.example .env   # Add your API keys
streamlit run app.py
```

### Configuration

Copy `.env.example` to `.env` and fill in your credentials:

```
GROQ_API_KEY="..."           # LLM generation
KIE_API_KEY="..."            # AI video generation
NOTION_API_KEY="..."         # Notion integration
NOTION_DATABASE_ID="..."     # Your Notion database ID
NOTION_VERSION="2022-06-28"
```

---

## Deployment (Streamlit Cloud)

1. Push this repo to GitHub
2. Go to [share.streamlit.io](https://share.streamlit.io) and connect your GitHub repo
3. Set `app.py` as the main file
4. Add your API keys under **Advanced Settings > Secrets** (TOML format)
5. Deploy — you'll get a shareable public URL

---

## Project Structure

```
├── app.py                  # Main application (UI + pipeline logic)
├── services/
│   ├── llm.py              # LLM API integration
│   ├── notion.py           # Notion database client
│   ├── validator.py        # Output validation
│   └── video.py            # AI video generation
├── docs/
│   └── architecture.md     # System architecture diagram
├── requirements.txt
├── .env.example
└── README.md
```

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Frontend | Streamlit |
| LLM | GROQ API (LLaMA 3.3 70B) |
| Video | KIE / Runway (Text-to-Video) |
| Database | Notion API |

---

## Architecture

```
┌─────────────────────────────────────────┐
│              AI DOMAIN                   │
│                                          │
│  LLM generates ad copy, headlines, CTAs  │
│  Video AI generates 5 visual assets      │
│  Validator ensures structural integrity  │
│                                          │
├──────────── HANDOFF ─────────────────────┤
│                                          │
│            HUMAN DOMAIN                  │
│                                          │
│  Review and tag generated creatives      │
│  Add notes and iteration feedback        │
│  Decide which ads go live                │
│  Allocate budget across funnel stages    │
│                                          │
└─────────────────────────────────────────┘
```
