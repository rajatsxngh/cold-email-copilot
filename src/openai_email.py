# src/openai_email.py
"""Use OpenAI to read the job description and write the email.

Both calls ask the model for JSON, so the answer can be read reliably.
"""
from __future__ import annotations

import json
import logging
import re

from . import config

log = logging.getLogger(__name__)

JD_SYSTEM_PROMPT = """You extract structured information from job descriptions.
Return a JSON object with exactly these keys:
- "role_title": string
- "company_name": string
- "location": string
- "top_skills": list of up to 8 short skills or keywords
Use an empty string or an empty list when something isn't mentioned."""

EMAIL_SYSTEM_PROMPT = """You write short, personalized cold emails from a job seeker to a recruiter about one specific role.
Tone: professional, warm and direct. Plain language, no buzzwords, no exaggeration.
Only mention experience that appears in the resume text you are given. Never invent achievements, numbers, employers or degrees.
Return a JSON object with two keys: "subject" and "body"."""

EMPTY_JD = {"role_title": "", "company_name": "", "location": "", "top_skills": []}


def _loads_json(text: str) -> dict:
    """Read JSON from a model reply, even if it's wrapped in a ```json code block."""
    match = re.search(r"\{.*\}", text or "", re.DOTALL)
    try:
        data = json.loads(match.group(0) if match else text)
    except (TypeError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def _chat_json(system: str, user: str, temperature: float) -> dict:
    from openai import BadRequestError

    client = config.get_openai_client()
    request = {
        "model": config.OPENAI_MODEL,
        "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
        "response_format": {"type": "json_object"},
        "temperature": temperature,
    }
    try:
        response = client.chat.completions.create(**request)
    except BadRequestError as exc:
        # some newer models only accept the default temperature
        if "temperature" not in str(exc):
            raise
        request.pop("temperature")
        response = client.chat.completions.create(**request)
    return _loads_json(response.choices[0].message.content)


def parse_jd(jd_text: str) -> dict:
    """Pull the role, company, location and top skills out of a job description."""
    if not (jd_text or "").strip():
        return dict(EMPTY_JD)
    data = _chat_json(JD_SYSTEM_PROMPT, jd_text, temperature=0.2)

    skills = data.get("top_skills") or []
    if isinstance(skills, str):
        skills = skills.split(",")
    return {
        "role_title": str(data.get("role_title") or "").strip(),
        "company_name": str(data.get("company_name") or "").strip(),
        "location": str(data.get("location") or "").strip(),
        "top_skills": [str(s).strip() for s in skills if str(s).strip()][:8],
    }


def generate_cold_email(
    jd_info: dict,
    resume_snippets: list[dict],
    recruiter_name: str,
    resume_header: str = "",
) -> tuple[str, str]:
    """Write a subject line and email body. Returns (subject, body)."""
    role = jd_info.get("role_title") or "this role"
    company = jd_info.get("company_name") or "your company"
    skills = ", ".join(jd_info.get("top_skills") or []) or "not listed"
    snippets_text = "\n".join(f"- {s['text']}" for s in resume_snippets) or "- (no resume matches found)"
    greeting_name = (recruiter_name or "").strip() or "(unknown, so greet them politely without a name)"

    user_prompt = f"""Role: {role}
Company: {company}
Top skills in the job description: {skills}
Recruiter name: {greeting_name}

Top of my resume (use it to find my name for the sign-off):
{resume_header or "(not available)"}

My most relevant experience, taken from my resume:
{snippets_text}

Write:
- "subject": one clear, specific subject line (under 10 words).
- "body": a 120-180 word email that greets the recruiter, names the role and company,
  highlights 2-3 concrete things from my experience that match the job, and politely asks
  for a short call or for my application to be considered. Sign off with my name if you can
  find it above, otherwise use [Your Name]."""

    data = _chat_json(EMAIL_SYSTEM_PROMPT, user_prompt, temperature=0.5)
    subject = str(data.get("subject") or "").strip() or f"Interest in the {role} role"
    body = str(data.get("body") or "").strip()
    return subject, body
