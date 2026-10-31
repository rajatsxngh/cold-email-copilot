# src/n8n_client.py
"""Send the finished email to an n8n webhook, which sends it through Gmail and can log it."""
from __future__ import annotations

import requests

from . import config

TIMEOUT_SECONDS = 10


def send_via_n8n(to: str, subject: str, body: str, job_title: str = "", company: str = "", jd_url: str = "") -> str:
    """Post the email to n8n. Returns a short status message for the app."""
    if not config.N8N_WEBHOOK_URL:
        return "⚠️ n8n isn't set up. Add N8N_WEBHOOK_URL to your .env, or use “Open in Gmail”."
    if not to or "@" not in to:
        return "⚠️ Add the recruiter's email address before sending."
    if not (subject or "").strip() or not (body or "").strip():
        return "⚠️ The subject and body can't be empty."

    payload = {
        "to": to.strip(),
        "subject": subject,
        "body": body,
        "job_title": job_title,
        "company": company,
        "jd_url": jd_url,
    }
    try:
        resp = requests.post(config.N8N_WEBHOOK_URL, json=payload, timeout=TIMEOUT_SECONDS)
    except requests.RequestException as exc:
        return f"❌ Couldn't reach n8n: {exc}"
    if resp.status_code in (200, 201, 204):
        return f"✅ Sent to {payload['to']} through n8n."
    return f"⚠️ n8n replied with {resp.status_code}: {resp.text[:200]}"
