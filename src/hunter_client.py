# src/hunter_client.py
"""Look up a recruiter's work email with Hunter.io.

1. Try Hunter's Email Finder with the recruiter's name and company domain.
2. If that finds nothing, search every email Hunter knows for the domain and
   look for an exact name match.

It never guesses: if the recruiter isn't found, it returns no email rather
than someone else's address at the same company.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass

import requests

from . import config

log = logging.getLogger(__name__)

HUNTER_BASE_URL = "https://api.hunter.io/v2"
TIMEOUT_SECONDS = 10


@dataclass
class RecruiterEmail:
    email: str | None
    source: str = ""  # which Hunter endpoint found it
    confidence: int | None = None  # Hunter's 0-100 confidence score
    message: str = ""  # short note shown in the app


def clean_domain(value: str) -> str:
    """Turn 'https://www.acme.com/careers' into 'acme.com'."""
    value = value.strip().lower()
    value = re.sub(r"^[a-z]+://", "", value)
    value = value.split("/")[0].split("?")[0]
    return value.removeprefix("www.")


def _split_name(full_name: str) -> tuple[str, str]:
    """Split 'John Dennis' into ('John', 'Dennis')."""
    parts = full_name.split()
    if not parts:
        return "", ""
    return parts[0], " ".join(parts[1:])


def _same_name(a: str, b: str) -> bool:
    return " ".join(a.casefold().split()) == " ".join(b.casefold().split())


def _error_text(resp: requests.Response) -> str:
    try:
        errors = resp.json().get("errors") or []
        return errors[0].get("details", "") if errors else ""
    except ValueError:
        return ""


def find_recruiter_email(full_name: str, domain: str) -> RecruiterEmail:
    if not config.HUNTER_API_KEY:
        return RecruiterEmail(None, message="Hunter isn't set up. Type the email yourself.")

    full_name = (full_name or "").strip()
    domain = clean_domain(domain or "")
    if not full_name or not domain:
        return RecruiterEmail(None, message="Add the recruiter's name and company domain to look up their email.")

    first, last = _split_name(full_name)
    params = {"domain": domain, "api_key": config.HUNTER_API_KEY}
    if last:
        params.update(first_name=first, last_name=last)
    else:
        params["full_name"] = full_name

    # 1) Email Finder
    try:
        resp = requests.get(f"{HUNTER_BASE_URL}/email-finder", params=params, timeout=TIMEOUT_SECONDS)
        if resp.status_code == 200:
            data = resp.json().get("data") or {}
            if data.get("email"):
                return RecruiterEmail(data["email"], "Email Finder", data.get("score"), "Found by Hunter Email Finder.")
        elif resp.status_code in (401, 403, 429):
            # bad key, no access, or out of credits: the next call would fail the same way
            return RecruiterEmail(None, message=f"Hunter error {resp.status_code}: {_error_text(resp) or resp.reason}")
        else:
            log.info("Hunter Email Finder returned %s", resp.status_code)
    except requests.RequestException as exc:
        log.warning("Hunter Email Finder failed: %s", exc)

    # 2) Domain Search, exact name match only
    try:
        resp = requests.get(
            f"{HUNTER_BASE_URL}/domain-search",
            params={"domain": domain, "api_key": config.HUNTER_API_KEY},
            timeout=TIMEOUT_SECONDS,
        )
        if resp.status_code == 200:
            for entry in (resp.json().get("data") or {}).get("emails", []):
                name = f"{entry.get('first_name') or ''} {entry.get('last_name') or ''}"
                if _same_name(name, full_name) and entry.get("value"):
                    return RecruiterEmail(entry["value"], "Domain Search", entry.get("confidence"), "Found by Hunter Domain Search.")
    except requests.RequestException as exc:
        log.warning("Hunter Domain Search failed: %s", exc)

    return RecruiterEmail(None, message=f"Hunter couldn't find {full_name} at {domain}. Type the email yourself.")
