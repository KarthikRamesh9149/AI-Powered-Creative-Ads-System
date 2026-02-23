"""Heidi — AI Creative Ads Generator.

Streamlit app that generates full-funnel ad creatives via GROQ LLM,
creates video assets via KIE API, and stores everything in Notion.

Run: set env vars in .env then `streamlit run app.py`.
"""

import os
import time
import uuid
from typing import Dict, List, Optional

import requests as _requests
import streamlit as st

try:
    from dotenv import load_dotenv
except Exception:
    load_dotenv = None

from services.llm import generate_creative_set, generate_single_creative
from services.notion import (
    NotionClient,
    build_notion_properties,
    build_tag_update_properties,
    build_update_properties,
    check_required_properties,
    database_url,
    extract_page_values,
    _build_property,
)
from services.validator import validate_payload, validate_single_creative
from services.video import create_video_task, get_video_status

APP_TITLE = "AI-Powered Creative Ads System"
FUNNEL_STAGES = ["Awareness", "Mid", "Conversion", "Full"]
TAG_OPTIONS = ["Draft", "Testing", "Needs Revision", "Approved", "Winner"]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _init_state() -> None:
    defaults = {
        "runs": {},
        "active_set_id": None,
        "last_error": None,
        "property_types": None,
        "notion_errors": [],
        "notion_check": None,
        "display_cards": [],
        "active_filter_set": None,
        "_poll_count": 0,
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value


def _credentials_ready() -> bool:
    return all(
        [
            os.getenv("GROQ_API_KEY"),
            os.getenv("KIE_API_KEY"),
            os.getenv("NOTION_API_KEY"),
            os.getenv("NOTION_DATABASE_ID"),
        ]
    )


def _get_notion_client() -> NotionClient:
    return NotionClient(
        api_key=os.getenv("NOTION_API_KEY", ""),
        database_id=os.getenv("NOTION_DATABASE_ID", ""),
        data_source_id=os.getenv("NOTION_DATA_SOURCE_ID"),
        notion_version=os.getenv("NOTION_VERSION", "2022-06-28"),
    )


def _safe_rerun() -> None:
    try:
        st.rerun()
    except AttributeError:
        st.experimental_rerun()


# ---------------------------------------------------------------------------
# Generation pipeline
# ---------------------------------------------------------------------------

def _start_generation(persona: str, market: str, funnel_stage: str) -> None:
    st.session_state["active_set_id"] = None
    st.session_state["last_error"] = None
    st.session_state["_poll_count"] = 0

    persona = persona.strip()
    market = market.strip()

    set_id = f"SET-{uuid.uuid4().hex[:10].upper()}"

    # Step 1: Call GROQ LLM
    try:
        payload = generate_creative_set(
            persona=persona,
            market=market,
            funnel_stage=funnel_stage,
            set_id=set_id,
            api_key=os.getenv("GROQ_API_KEY", ""),
        )
    except Exception as exc:
        st.session_state["last_error"] = f"Creative generation failed: {exc}"
        return

    # Step 2: Validate schema
    ok, error_msg = validate_payload(
        payload,
        expected_inputs={"persona": persona, "market": market, "funnel_stage": funnel_stage},
        expected_set_id=set_id,
    )
    if not ok:
        st.session_state["last_error"] = error_msg
        return

    # Step 3: Store in session
    run_state: Dict = {
        "set_id": set_id,
        "payload": payload,
        "creatives": payload["creatives"],
        "videos": payload["videos"],
        "video_tasks": {},
        "video_urls": {},
        "creative_status": {c["ad_label"]: {"status": "pending"} for c in payload["creatives"]},
        "notion_pages": {},
        "notion_created": False,
    }
    st.session_state["runs"][set_id] = run_state
    st.session_state["active_set_id"] = set_id

    # Step 4: Create Notion pages
    _create_notion_rows(run_state)

    # Step 5: Start video generation
    for video in payload["videos"]:
        video_id = video["video_id"]
        try:
            task_id = create_video_task(
                prompt=video["prompt"],
                api_key=os.getenv("KIE_API_KEY", ""),
                callback_url=os.getenv("KIE_CALLBACK_URL", ""),
            )
            run_state["video_tasks"][video_id] = {
                "task_id": task_id, "status": "pending",
                "video_url": None, "error": None,
                "attempts": 0, "next_poll_at": time.time(),
            }
        except Exception as exc:
            run_state["video_tasks"][video_id] = {
                "task_id": None, "status": "fail",
                "video_url": None, "error": str(exc),
                "attempts": 1, "next_poll_at": time.time(),
            }

    st.session_state["runs"][set_id] = run_state

    # Step 6: Auto-load from Notion so cards appear immediately
    try:
        st.session_state["display_cards"] = _query_notion_set(set_id)
    except Exception:
        st.session_state["display_cards"] = []
    st.session_state["active_filter_set"] = set_id


def _create_notion_rows(run_state: Dict) -> None:
    notion = _get_notion_client()
    if st.session_state.get("property_types") is None:
        try:
            st.session_state["property_types"] = notion.get_property_types()
        except Exception:
            st.session_state["property_types"] = None

    property_types = st.session_state.get("property_types")
    errors: list = []
    success_count = 0
    for creative in run_state["creatives"]:
        ad_label = creative["ad_label"]
        try:
            properties = build_notion_properties(
                creative=creative,
                inputs=run_state["payload"]["inputs"],
                set_id=run_state["payload"]["set_id"],
                video_url=None,
                status="Not started",
                property_types=property_types,
            )
            page = notion.create_page(properties)
            run_state["notion_pages"][ad_label] = page.get("id")
            run_state["creative_status"][ad_label]["status"] = "saved"
            success_count += 1
        except Exception as exc:
            run_state["creative_status"][ad_label]["status"] = "error"
            run_state["creative_status"][ad_label]["error"] = str(exc)
            errors.append(f"Ad {ad_label}: {exc}")

    run_state["notion_attempted"] = True
    run_state["notion_created"] = success_count == len(run_state["creatives"])
    st.session_state["notion_errors"] = errors


def _regenerate_ad(
    page_id: str,
    ad_label: str,
    persona: str,
    market: str,
    funnel_stage: str,
    video_id: str,
    language: str,
    feedback: str,
    current_iteration: int,
) -> Dict:
    result = generate_single_creative(
        ad_label=ad_label,
        persona=persona,
        market=market,
        funnel_stage=funnel_stage,
        language=language,
        video_id=video_id,
        feedback=feedback,
        api_key=os.getenv("GROQ_API_KEY", ""),
    )
    ok, err = validate_single_creative(result, ad_label)
    if not ok:
        return {"status": "error", "message": err}

    # Update Notion page with new content
    notion = _get_notion_client()
    pt = notion.get_property_types()
    new_iter = current_iteration + 1
    props = build_update_properties(video_url=None, status="Generated", property_types=pt)
    if "Headline" in pt:
        props["Headline"] = _build_property(result["headline"], pt["Headline"])
    if "Primary Text" in pt:
        props["Primary Text"] = _build_property(result["primary_text"], pt["Primary Text"])
    if "CTA" in pt:
        props["CTA"] = _build_property(result["cta"], pt["CTA"])
    if "Iteration" in pt:
        props["Iteration"] = {"number": new_iter}

    notion.update_page(page_id, props)
    return {
        "status": "success",
        "iteration": new_iter,
        "headline": result["headline"],
        "primary_text": result["primary_text"],
        "cta": result["cta"],
    }


# ---------------------------------------------------------------------------
# Video polling
# ---------------------------------------------------------------------------

def _poll_videos() -> None:
    run_state = _get_active_run()
    if not run_state:
        return
    api_key = os.getenv("KIE_API_KEY", "")
    for video_id, task in run_state.get("video_tasks", {}).items():
        if task.get("status") in ("success", "fail"):
            continue
        if not task.get("task_id"):
            continue
        if time.time() < task.get("next_poll_at", 0):
            continue
        if task.get("attempts", 0) >= 60:
            task["status"] = "fail"
            task["error"] = "Timed out waiting for video."
            _update_notion_for_video(video_id, task)
            continue
        try:
            state, video_url, error = get_video_status(task["task_id"], api_key)
        except Exception as exc:
            state, video_url, error = "fail", None, str(exc)

        if state == "success":
            task.update(status="success", video_url=video_url, error=None)
            run_state["video_urls"][video_id] = video_url
            _update_notion_for_video(video_id, task)
        elif state == "fail":
            task.update(status="fail", video_url=None, error=error or "Video generation failed")
            _update_notion_for_video(video_id, task)
        else:
            task["attempts"] = task.get("attempts", 0) + 1
            task["next_poll_at"] = time.time() + 5


def _update_notion_for_video(video_id: str, task: Dict) -> None:
    run_state = _get_active_run()
    if not run_state:
        return
    notion = _get_notion_client()
    property_types = st.session_state.get("property_types")
    status_label = "Generated" if task.get("status") == "success" else "Iterating"
    video_url = task.get("video_url") if task.get("status") == "success" else None

    for creative in run_state["creatives"]:
        if creative["video_id"] != video_id:
            continue
        page_id = run_state["notion_pages"].get(creative["ad_label"])
        if not page_id:
            continue
        try:
            props = build_update_properties(video_url=video_url, status=status_label, property_types=property_types)
            notion.update_page(page_id, props)
        except Exception:
            pass


def _get_active_run() -> Optional[Dict]:
    set_id = st.session_state.get("active_set_id")
    if not set_id:
        return None
    return st.session_state.get("runs", {}).get(set_id)


# ---------------------------------------------------------------------------
# Notion queries
# ---------------------------------------------------------------------------

def _query_notion_set(set_id: str) -> List[Dict]:
    notion = _get_notion_client()
    pt = notion.get_property_types()
    set_id_type = pt.get("Set ID", "rich_text")
    if set_id_type == "title":
        filter_obj = {"property": "Set ID", "title": {"equals": set_id}}
    else:
        filter_obj = {"property": "Set ID", "rich_text": {"equals": set_id}}
    pages = notion.query_database(filter_obj=filter_obj)
    return [extract_page_values(p) for p in pages]


def _query_all_sets() -> List[str]:
    notion = _get_notion_client()
    pages = notion.query_database(
        sorts=[{"timestamp": "created_time", "direction": "descending"}],
    )
    seen = []
    for p in pages:
        vals = extract_page_values(p)
        sid = vals.get("Set ID", "") or vals.get("Headline", "")
        if sid and sid not in seen:
            seen.append(sid)
    return seen


def _load_cards(set_filter: str = "All") -> None:
    try:
        notion = _get_notion_client()
        pt = notion.get_property_types()
        filter_obj = None
        if set_filter != "All":
            set_id_type = pt.get("Set ID", "rich_text")
            if set_id_type == "title":
                filter_obj = {"property": "Set ID", "title": {"equals": set_filter}}
            else:
                filter_obj = {"property": "Set ID", "rich_text": {"equals": set_filter}}
        pages = notion.query_database(
            filter_obj=filter_obj,
            sorts=[{"timestamp": "created_time", "direction": "descending"}],
        )
        st.session_state["display_cards"] = [extract_page_values(p) for p in pages]
    except Exception as exc:
        st.error(f"Failed to load creatives: {exc}")
        st.session_state["display_cards"] = []


def _update_tag(page_id: str, tag: str) -> None:
    notion = _get_notion_client()
    pt = notion.get_property_types()
    props = build_tag_update_properties(property_types=pt, tag=tag)
    if props:
        notion.update_page(page_id, props)


def _update_notes(page_id: str, notes: str) -> None:
    notion = _get_notion_client()
    pt = notion.get_property_types()
    props = build_tag_update_properties(property_types=pt, notes=notes)
    if props:
        notion.update_page(page_id, props)


# ---------------------------------------------------------------------------
# Notion check
# ---------------------------------------------------------------------------

def _check_notion_only() -> None:
    notion = _get_notion_client()
    try:
        property_types = notion.get_property_types()
        required = check_required_properties(property_types)
        missing = [name for name, ptype in required.items() if not ptype]
        st.session_state["notion_check"] = {
            "ok": len(missing) == 0,
            "error": "",
            "missing": missing,
            "types": required,
        }
        st.session_state["property_types"] = property_types
    except Exception as exc:
        st.session_state["notion_check"] = {
            "ok": False,
            "error": str(exc),
            "missing": [],
            "types": {},
        }


# ---------------------------------------------------------------------------
# UI: CSS
# ---------------------------------------------------------------------------

_CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=DM+Sans:ital,opsz,wght@0,9..40,300;0,9..40,400;0,9..40,500;0,9..40,600;0,9..40,700&family=JetBrains+Mono:wght@400;500&display=swap');
:root {
  --bark: #28030f;
  --bark-light: #3d1520;
  --sand: #f6ece4;
  --sand-dark: #ede0d4;
  --green: #1f5c2a;
  --green-light: #2b6433;
  --green-pale: #e8f5e9;
  --yellow: #fbf582;
  --yellow-bright: #fdf444;
  --ink: #28030f;
  --muted: #6d4c5a;
  --card: #ffffff;
  --card-hover: #fefcfa;
  --border: #e8d8ce;
  --border-light: #f0e6de;
}

/* === Global === */
html, body, [class*="stApp"] {
  background: linear-gradient(160deg, #faf5f0 0%, var(--sand) 40%, #f0e4d8 100%) !important;
  color: var(--ink);
  font-family: "DM Sans", -apple-system, BlinkMacSystemFont, sans-serif;
}

/* === Hero header === */
.heidi-hero {
  background: linear-gradient(135deg, var(--bark) 0%, var(--bark-light) 60%, #4a1a2e 100%);
  border-radius: 20px;
  padding: 2.5rem 2.5rem 2rem;
  margin-bottom: 1.8rem;
  position: relative;
  overflow: hidden;
  text-align: center;
}
.heidi-hero::before {
  content: "";
  position: absolute;
  top: -40px;
  right: -40px;
  width: 200px;
  height: 200px;
  background: radial-gradient(circle, var(--yellow) 0%, transparent 70%);
  opacity: 0.12;
  border-radius: 50%;
}
.heidi-hero h1 {
  color: var(--sand) !important;
  font-size: 2.2rem !important;
  font-weight: 700 !important;
  margin: 0 0 0.5rem 0 !important;
  letter-spacing: -0.02em;
}
.heidi-hero .subtitle {
  color: #c9a8b0;
  font-size: 1rem;
  margin: 0;
  font-weight: 400;
}
.heidi-badge {
  display: inline-block;
  background: var(--yellow);
  color: var(--bark);
  font-weight: 600;
  font-size: 0.7rem;
  padding: 0.2rem 0.6rem;
  border-radius: 999px;
  text-transform: uppercase;
  letter-spacing: 0.06em;
  margin-left: 0.6rem;
  vertical-align: middle;
}

/* === Buttons === */
.stButton>button {
  background: linear-gradient(135deg, var(--green) 0%, var(--green-light) 100%);
  color: #ffffff;
  border-radius: 12px;
  border: none;
  padding: 0.65rem 1.5rem;
  font-weight: 600;
  font-family: "DM Sans", sans-serif;
  font-size: 0.9rem;
  transition: all 0.2s ease;
  box-shadow: 0 2px 8px rgba(31,92,42,0.15);
}
.stButton>button:hover {
  background: linear-gradient(135deg, var(--green-light) 0%, #358040 100%);
  box-shadow: 0 4px 16px rgba(31,92,42,0.25);
  transform: translateY(-1px);
}
.stButton>button:active {
  transform: translateY(0px);
}

/* === Inputs === */
.stTextInput input, .stSelectbox div[data-baseweb="select"] {
  border-radius: 12px !important;
  border-color: var(--border) !important;
  font-family: "DM Sans", sans-serif !important;
}
.stTextInput input:focus {
  border-color: var(--green) !important;
  box-shadow: 0 0 0 2px rgba(31,92,42,0.12) !important;
}
.stTextArea textarea {
  border-radius: 12px !important;
  border-color: var(--border) !important;
  font-family: "DM Sans", sans-serif !important;
}

/* === Cards === */
.card {
  background: var(--card);
  border: 1px solid var(--border);
  border-radius: 16px;
  padding: 1.3rem 1.5rem;
  margin-bottom: 1rem;
  box-shadow: 0 1px 4px rgba(40,3,15,0.04);
  transition: box-shadow 0.2s ease;
}
.card:hover {
  box-shadow: 0 4px 16px rgba(40,3,15,0.08);
}
.ad-header {
  font-weight: 700;
  font-size: 1.05rem;
  margin-bottom: 0.5rem;
  color: var(--bark);
  display: flex;
  align-items: center;
  gap: 0.5rem;
  flex-wrap: wrap;
}
.ad-badge {
  display: inline-block;
  background: linear-gradient(135deg, var(--green) 0%, var(--green-light) 100%);
  color: #fff;
  font-size: 0.72rem;
  font-weight: 600;
  padding: 0.15rem 0.55rem;
  border-radius: 6px;
  letter-spacing: 0.02em;
}
.ad-funnel {
  display: inline-block;
  background: var(--green);
  color: #fff;
  font-size: 0.85rem;
  font-weight: 600;
  padding: 0.35rem 0.75rem;
  border-radius: 8px;
  letter-spacing: 0.3px;
  border: none;
}
.ad-lang {
  display: inline-block;
  background: var(--yellow);
  color: var(--bark);
  font-size: 0.68rem;
  font-weight: 600;
  padding: 0.12rem 0.45rem;
  border-radius: 5px;
}

/* === Meta & Video === */
.video-meta, .meta {
  font-family: "JetBrains Mono", monospace;
  font-size: 0.8rem;
  color: var(--muted);
}
.set-meta {
  font-family: "JetBrains Mono", monospace;
  font-size: 0.82rem;
  color: var(--muted);
  background: rgba(40,3,15,0.03);
  padding: 0.5rem 0.8rem;
  border-radius: 10px;
  display: inline-block;
  margin-top: 0.5rem;
}

/* === Notion link === */
.notion-link {
  display: inline-flex;
  align-items: center;
  gap: 0.4rem;
  margin-top: 1rem;
  padding: 0.55rem 1.2rem;
  background: var(--card);
  border: 1px solid var(--border);
  border-radius: 999px;
  text-decoration: none;
  color: var(--bark);
  font-weight: 600;
  font-size: 0.88rem;
  transition: all 0.2s ease;
  box-shadow: 0 1px 4px rgba(40,3,15,0.06);
}
.notion-link:hover {
  border-color: var(--green);
  color: var(--green);
  box-shadow: 0 2px 12px rgba(31,92,42,0.12);
}

/* === Tags === */
.tag-winner {
  background: #dcfce7; color: #15803d; font-weight: 700;
  padding: 0.12rem 0.5rem; border-radius: 6px; font-size: 0.78rem;
}
.tag-approved {
  background: var(--green-pale); color: var(--green); font-weight: 600;
  padding: 0.12rem 0.5rem; border-radius: 6px; font-size: 0.78rem;
}
.tag-testing {
  background: #fef3c7; color: #92400e;
  padding: 0.12rem 0.5rem; border-radius: 6px; font-size: 0.78rem;
}
.tag-needs-revision {
  background: #fee2e2; color: #dc2626;
  padding: 0.12rem 0.5rem; border-radius: 6px; font-size: 0.78rem;
}
.tag-draft {
  background: #f3f4f6; color: #6b7280;
  padding: 0.12rem 0.5rem; border-radius: 6px; font-size: 0.78rem;
}

/* === Progress === */
.stProgress > div > div {
  background: linear-gradient(90deg, var(--green) 0%, var(--green-light) 100%) !important;
  border-radius: 999px;
}

/* === Metrics === */
[data-testid="stMetric"] {
  background: var(--card);
  border: 1px solid var(--border-light);
  border-radius: 14px;
  padding: 0.8rem 1rem;
  box-shadow: 0 1px 3px rgba(40,3,15,0.03);
}
[data-testid="stMetric"] label {
  color: var(--muted) !important;
  font-size: 0.78rem !important;
  font-weight: 500 !important;
}
[data-testid="stMetric"] [data-testid="stMetricValue"] {
  color: var(--bark) !important;
  font-weight: 700 !important;
}

/* === Section titles === */
.section-title {
  color: var(--bark);
  font-size: 1.15rem;
  font-weight: 700;
  margin: 1.5rem 0 0.8rem 0;
  display: flex;
  align-items: center;
  gap: 0.4rem;
}
.section-divider {
  height: 2px;
  background: linear-gradient(90deg, var(--green) 0%, var(--yellow) 50%, transparent 100%);
  border: none;
  border-radius: 2px;
  margin: 1.2rem 0;
}

/* === Expander === */
.streamlit-expanderHeader {
  font-weight: 600 !important;
  color: var(--bark) !important;
  font-family: "DM Sans", sans-serif !important;
}

/* === Hide default Streamlit branding === */
#MainMenu { visibility: hidden; }
footer { visibility: hidden; }
header { visibility: hidden; }
</style>
"""


# ---------------------------------------------------------------------------
# UI: Generation Form
# ---------------------------------------------------------------------------

def _render_generation_form() -> None:
    with st.expander("Generate New Set", expanded=not st.session_state.get("active_set_id")):
        col1, col2 = st.columns(2)
        with col1:
            persona = st.text_input("Persona", placeholder="E.g. busy wellness-focused parent", key="persona_input")
        with col2:
            market = st.text_input("Market", placeholder="E.g. US subscription skincare", key="market_input")

        col3, col4 = st.columns([2, 1.5])
        with col3:
            funnel_stage = st.selectbox("Funnel Stage", FUNNEL_STAGES, index=3)
        with col4:
            st.markdown("<div style='height:1.6rem'></div>", unsafe_allow_html=True)
            generate = st.button("\U0001f680 Generate Ads", use_container_width=True)

        if generate:
            if not persona or not market:
                st.session_state["last_error"] = "Persona and Market are required."
            elif not _credentials_ready():
                st.session_state["last_error"] = "Required credentials are not configured."
            else:
                st.session_state["last_error"] = None
                with st.spinner("Generating ad creatives and videos..."):
                    _start_generation(persona, market, funnel_stage)

    if st.session_state.get("last_error"):
        st.error(st.session_state["last_error"])


# ---------------------------------------------------------------------------
# UI: Video Generation Progress
# ---------------------------------------------------------------------------

def _render_generation_progress() -> None:
    run_state = _get_active_run()
    if not run_state:
        return

    video_tasks = run_state.get("video_tasks", {})
    if not video_tasks:
        return

    done_videos = sum(1 for v in video_tasks.values() if v.get("status") == "success")
    failed_videos = sum(1 for v in video_tasks.values() if v.get("status") == "fail")
    pending_videos = len(video_tasks) - done_videos - failed_videos
    total_videos = max(len(video_tasks), 1)

    st.markdown("<div class='section-divider'></div>", unsafe_allow_html=True)
    st.markdown("<div class='section-title'>Video Generation Progress</div>", unsafe_allow_html=True)
    st.markdown(
        f"<div class='set-meta'>Set ID: <code>{run_state['set_id']}</code> &nbsp;&middot;&nbsp; "
        f"{len(run_state.get('creatives', []))} ads &nbsp;&middot;&nbsp; {len(run_state.get('videos', []))} videos</div>",
        unsafe_allow_html=True,
    )

    st.progress(done_videos / total_videos)
    col1, col2, col3 = st.columns(3)
    col1.metric("Videos Complete", done_videos)
    col2.metric("Videos Pending", pending_videos)
    col3.metric("Videos Failed", failed_videos)

    if failed_videos:
        st.warning(f"{failed_videos} video(s) failed. Text ads are still available.")

    if st.session_state.get("notion_errors"):
        with st.expander("Storage errors"):
            for e in st.session_state["notion_errors"]:
                st.error(e)

    # Notion link
    if run_state.get("notion_created"):
        db_url = os.getenv("NOTION_DB_VIEW_URL") or database_url(os.getenv("NOTION_DATABASE_ID", ""))
        st.markdown(
            f"<a class='notion-link' href='{db_url}' target='_blank'>\U0001f4c4 View in Notion</a>",
            unsafe_allow_html=True,
        )

    # Poll and auto-refresh if videos still pending
    if pending_videos > 0:
        _poll_videos()

        # Refresh display cards from Notion so video URLs appear
        set_id = st.session_state.get("active_set_id")
        if set_id:
            try:
                st.session_state["display_cards"] = _query_notion_set(set_id)
                st.session_state["active_filter_set"] = set_id
            except Exception:
                pass

        poll_count = st.session_state.get("_poll_count", 0)
        if poll_count < 120:
            st.session_state["_poll_count"] = poll_count + 1
            st.caption(f"Generating videos... ({done_videos}/{total_videos} complete)")
            time.sleep(3)
            _safe_rerun()
        else:
            st.warning("Video generation timed out. Click Refresh to check status.")
    else:
        st.session_state["_poll_count"] = 0


# ---------------------------------------------------------------------------
# UI: Filters
# ---------------------------------------------------------------------------

def _render_filters() -> List[Dict]:
    col_f1, col_f2, col_f3, col_f4 = st.columns([2, 1.5, 1.5, 1])
    with col_f1:
        try:
            all_sets = _query_all_sets()
        except Exception:
            all_sets = []
        active_filter = st.session_state.get("active_filter_set")
        default_idx = 0
        if active_filter and active_filter in all_sets:
            default_idx = all_sets.index(active_filter) + 1
        set_filter = st.selectbox("Set ID", ["All"] + all_sets, index=default_idx, key="mgr_set_filter")
    with col_f2:
        stage_filter = st.selectbox("Funnel Stage", ["All"] + FUNNEL_STAGES, key="mgr_stage_filter")
    with col_f3:
        tag_filter = st.selectbox("Tag", ["All"] + TAG_OPTIONS, key="mgr_tag_filter")
    with col_f4:
        st.markdown("<div style='height:1.6rem'></div>", unsafe_allow_html=True)
        refresh = st.button("\U0001f504 Refresh", use_container_width=True, key="mgr_refresh")

    if refresh:
        _load_cards(set_filter)

    cards = st.session_state.get("display_cards", [])

    # Client-side filters
    if stage_filter != "All":
        cards = [c for c in cards if c.get("Funnel Stage") == stage_filter]
    if tag_filter != "All":
        cards = [c for c in cards if c.get("Tag", "Draft") == tag_filter]

    return cards


# ---------------------------------------------------------------------------
# UI: Creative Card
# ---------------------------------------------------------------------------

def _render_card(card: Dict) -> None:
    ad_label = card.get("Ad Label", "?")
    page_id = card.get("page_id", "")
    unique = f"{page_id}_{ad_label}"

    with st.container():
        st.markdown("<div class='card'>", unsafe_allow_html=True)

        # Header
        funnel = card.get("Funnel Stage", "")
        lang = card.get("Language", "")
        status = card.get("Status", "")
        iteration = card.get("Iteration", 1) or 1
        set_id = card.get("Set ID", "")
        tag = card.get("Tag", "Draft") or "Draft"

        tag_class = f"tag-{tag.lower().replace(' ', '-')}"
        st.markdown(
            f"<div class='ad-header'>"
            f"<span class='ad-badge'>Ad {ad_label}</span>"
            f"<span class='ad-funnel'>{funnel}</span>"
            f"<span class='ad-lang'>{lang}</span>"
            f"<span class='{tag_class}'>{tag}</span>"
            f"</div>",
            unsafe_allow_html=True,
        )
        if set_id:
            st.markdown(
                f"<div class='meta'>Set: {set_id}</div>",
                unsafe_allow_html=True,
            )

        # Content
        headline = card.get("Headline", "")
        if headline:
            st.markdown(f"**{headline}**")
        primary_text = card.get("Primary Text", "")
        if primary_text:
            st.write(primary_text)
        cta = card.get("CTA", "")
        if cta:
            st.markdown(f"**CTA:** {cta}")

        reused = card.get("Reused?", False)
        video_id = card.get("Video ID", "")
        video_url = card.get("Video URL", "")
        if video_id:
            reused_label = " (reused)" if reused else ""
            st.markdown(f"<div class='video-meta'>Video: {video_id}{reused_label}</div>", unsafe_allow_html=True)
        if video_url:
            st.video(video_url)

        # Tag selector
        if page_id:
            col_tag, col_save = st.columns([3, 1])
            with col_tag:
                current_idx = TAG_OPTIONS.index(tag) if tag in TAG_OPTIONS else 0
                new_tag = st.selectbox(
                    "Tag",
                    TAG_OPTIONS,
                    index=current_idx,
                    key=f"tag_{unique}",
                    label_visibility="collapsed",
                )
            with col_save:
                if st.button("Save Tag", key=f"save_tag_{unique}"):
                    try:
                        _update_tag(page_id, new_tag)
                        st.success(f"Tag updated to {new_tag}")
                    except Exception as exc:
                        st.error(f"Failed: {exc}")

            # Notes
            current_notes = card.get("Notes", "") or ""
            notes = st.text_area("Notes", value=current_notes, key=f"notes_{unique}", height=68)
            if st.button("Save Notes", key=f"save_notes_{unique}"):
                try:
                    _update_notes(page_id, notes)
                    st.success("Notes saved")
                except Exception as exc:
                    st.error(f"Failed: {exc}")

            # Regenerate
            with st.expander("Regenerate this ad"):
                feedback = st.text_area(
                    "Feedback / instructions",
                    placeholder="E.g. Make the headline shorter and punchier",
                    key=f"regen_fb_{unique}",
                    height=68,
                )
                if st.button("Regenerate", key=f"regen_btn_{unique}"):
                    if not feedback.strip():
                        st.warning("Provide feedback for regeneration.")
                    else:
                        with st.spinner("Regenerating ad copy..."):
                            try:
                                persona = card.get("Persona", "")
                                market_val = card.get("Market", "")
                                res = _regenerate_ad(
                                    page_id=page_id,
                                    ad_label=ad_label,
                                    persona=persona,
                                    market=market_val,
                                    funnel_stage=funnel,
                                    video_id=video_id,
                                    language=lang,
                                    feedback=feedback,
                                    current_iteration=int(iteration),
                                )
                                if res.get("status") == "success":
                                    st.success(f"Regenerated! Now on iteration {res.get('iteration')}")
                                    st.markdown(f"**New headline:** {res.get('headline')}")
                                    st.write(res.get("primary_text"))
                                    st.markdown(f"**New CTA:** {res.get('cta')}")
                                else:
                                    st.error(res.get("message", "Regeneration failed"))
                            except Exception as exc:
                                st.error(f"Regeneration failed: {exc}")

        st.markdown("</div>", unsafe_allow_html=True)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    if load_dotenv:
        load_dotenv()
    st.set_page_config(page_title=APP_TITLE, page_icon="\U0001f3a8", layout="wide")
    _init_state()
    st.markdown(_CSS, unsafe_allow_html=True)

    # Hero header
    st.markdown(
        """<div class='heidi-hero'>
            <h1>AI-Powered Creative Ads System</h1>
            <p class='subtitle'>Generate full-funnel ad creatives, AI videos, and sync everything to Notion.</p>
        </div>""",
        unsafe_allow_html=True,
    )

    # Section 1: Generation form
    _render_generation_form()

    # Section 2: Video progress (only visible during active polling)
    _render_generation_progress()

    # Section 3: Creative cards from Notion
    st.markdown("<div class='section-divider'></div>", unsafe_allow_html=True)
    st.markdown("<div class='section-title'>Creative Manager</div>", unsafe_allow_html=True)
    st.caption("Browse, tag, annotate, and regenerate your ad creatives.")

    cards = _render_filters()

    if not cards:
        st.info("No creatives loaded. Generate a new set or click Refresh.")
    else:
        st.markdown(f"**{len(cards)}** creatives found")
        for card in cards:
            _render_card(card)


if __name__ == "__main__":
    main()
