import json
from typing import Dict, Tuple

import requests


GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
MODEL_ID = "llama-3.3-70b-versatile"

def _call_groq(payload: Dict, api_key: str) -> str:
    response = requests.post(
        GROQ_URL,
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        data=json.dumps(payload),
        timeout=60,
    )
    if response.status_code >= 300:
        raise RuntimeError(f"Upstream error ({response.status_code}).")

    data = response.json()
    content = data.get("choices", [{}])[0].get("message", {}).get("content")
    if not content:
        raise RuntimeError("Empty response.")
    return content


def _parse_json(content: str) -> Tuple[bool, Dict, str]:
    try:
        return True, json.loads(content), ""
    except Exception as exc:
        return False, {}, str(exc)


def generate_creative_set(
    persona: str,
    market: str,
    funnel_stage: str,
    set_id: str,
    api_key: str,
) -> Dict:
    if not api_key:
        raise RuntimeError("Missing API key.")

    system_prompt = (
        "You are a creative ads generator. Return STRICT JSON only. "
        "No markdown, no commentary, no extra text. Output must parse as JSON."
    )

    user_prompt = f"""
Generate ad creatives and video prompts for the following inputs:
Persona: {persona}
Market: {market}
Primary funnel focus: {funnel_stage}

Output schema (JSON only):
{{
  "set_id": "{set_id}",
  "inputs": {{
    "persona": "{persona}",
    "market": "{market}",
    "funnel_stage": "{funnel_stage}"
  }},
  "videos": [
    {{"video_id": "V1", "prompt": "..."}},
    {{"video_id": "V2", "prompt": "..."}},
    {{"video_id": "V3", "prompt": "..."}},
    {{"video_id": "V4", "prompt": "..."}},
    {{"video_id": "V5", "prompt": "..."}}
  ],
  "creatives": [
    {{
      "ad_label": "A",
      "funnel_stage": "Awareness",
      "language": "EN",
      "headline": "...",
      "primary_text": "...",
      "cta": "...",
      "video_id": "V1",
      "reused": false
    }}
  ]
}}

Rules:
- Return STRICT JSON only. No code fences.
- Use the exact set_id shown.
- Create exactly 5 video prompts (V1-V5). Each prompt must be a distinct visual concept aligned to its funnel intent.
- Create exactly 7 creatives with labels A-G and the mapping below:
  A: Awareness, EN, uses V1
  B: Awareness, EN, uses V2
  C: Awareness, EN, uses V3
  D: Mid, EN, uses V4
  E: Mid, EN, uses V4 (copy variant)
  F: Conversion, EN, uses V5
  G: Spanish copy, ES, uses V4
- Reused flag must be true only for E and G. All others false.
- Primary text should be 1-3 short paragraphs.
- Avoid mentioning tools, models, or providers.
""".strip()

    payload = {
        "model": MODEL_ID,
        "temperature": 0.7,
        "max_tokens": 2000,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
    }

    content = _call_groq(payload, api_key)
    ok, parsed, err = _parse_json(content)
    if ok:
        return parsed

    retry_payload = {
        "model": MODEL_ID,
        "temperature": 0.2,
        "max_tokens": 2000,
        "messages": [
            {
                "role": "system",
                "content": system_prompt
                + " Your previous response failed to parse. Return valid JSON only.",
            },
            {"role": "user", "content": user_prompt},
        ],
    }
    content = _call_groq(retry_payload, api_key)
    ok, parsed, retry_err = _parse_json(content)
    if ok:
        return parsed
    raise RuntimeError(f"Invalid JSON from model. {err} / {retry_err}")


def generate_single_creative(
    ad_label: str,
    persona: str,
    market: str,
    funnel_stage: str,
    language: str,
    video_id: str,
    feedback: str,
    api_key: str,
) -> Dict:
    if not api_key:
        raise RuntimeError("Missing API key.")

    reused = ad_label in ("E", "G")

    system_prompt = (
        "You are a creative ads generator. Return STRICT JSON only. "
        "No markdown, no commentary, no extra text. "
        "Generate a single ad creative based on the specifications and user feedback."
    )

    user_prompt = f"""
Regenerate ad creative {ad_label} with the following specifications:
Persona: {persona}
Market: {market}
Funnel Stage: {funnel_stage}
Language: {language}
Video ID: {video_id}

User feedback on the previous version: {feedback}

Return JSON:
{{
  "ad_label": "{ad_label}",
  "funnel_stage": "{funnel_stage}",
  "language": "{language}",
  "headline": "...",
  "primary_text": "...",
  "cta": "...",
  "video_id": "{video_id}",
  "reused": {str(reused).lower()}
}}

Rules:
- Return STRICT JSON only. No code fences.
- Incorporate the user feedback into the new copy.
- Primary text should be 1-3 short paragraphs.
- Avoid mentioning tools, models, or providers.
""".strip()

    payload = {
        "model": MODEL_ID,
        "temperature": 0.7,
        "max_tokens": 800,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
    }

    content = _call_groq(payload, api_key)
    ok, parsed, err = _parse_json(content)
    if ok:
        return parsed

    retry_payload = {
        "model": MODEL_ID,
        "temperature": 0.2,
        "max_tokens": 800,
        "messages": [
            {
                "role": "system",
                "content": system_prompt
                + " Your previous response failed to parse. Return valid JSON only.",
            },
            {"role": "user", "content": user_prompt},
        ],
    }
    content = _call_groq(retry_payload, api_key)
    ok, parsed, retry_err = _parse_json(content)
    if ok:
        return parsed
    raise RuntimeError(f"Invalid JSON from model. {err} / {retry_err}")
