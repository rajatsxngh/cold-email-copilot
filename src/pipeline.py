# src/pipeline.py
"""The main flow: resume + job description in, ready-to-send email out.

Kept separate from the UI so it can be tested on its own.
"""
from __future__ import annotations

import urllib.parse
from dataclasses import dataclass
from typing import Callable

from .embeddings_index import find_relevant_snippets
from .hunter_client import RecruiterEmail, find_recruiter_email
from .openai_email import generate_cold_email, parse_jd
from .pdf_utils import extract_text_from_pdf

STEPS = [
    "Reading your resume",
    "Reading the job description",
    "Matching your experience to the job",
    "Looking up the recruiter's email",
    "Writing your email",
]
MIN_JD_WORDS = 20


class InputError(ValueError):
    """Something the user entered is missing or can't be used."""


@dataclass
class CopilotResult:
    jd: dict
    snippets: list[dict]
    search_source: str  # "pinecone" or "in-memory"
    recruiter: RecruiterEmail
    subject: str
    body: str


def build_gmail_link(to: str, subject: str, body: str) -> str:
    """A Gmail compose link with the recipient, subject and body filled in."""
    query = urllib.parse.urlencode(
        {"view": "cm", "fs": "1", "to": to or "", "su": subject or "", "body": body or ""},
        quote_via=urllib.parse.quote,
    )
    return f"https://mail.google.com/mail/?{query}"


def run_pipeline(
    resume_path: str | None,
    jd_text: str,
    recruiter_name: str = "",
    company_domain: str = "",
    report: Callable[[int, str], None] = lambda step, label: None,
) -> CopilotResult:
    """Run every step. `report(step_number, label)` is called as each step starts."""
    jd_text = (jd_text or "").strip()
    if not resume_path:
        raise InputError("Upload your resume (PDF) first.")
    if not str(resume_path).lower().endswith(".pdf"):
        raise InputError("Your resume needs to be a PDF file.")
    if len(jd_text.split()) < MIN_JD_WORDS:
        raise InputError("Paste the full job description. What's there now looks too short.")

    report(0, STEPS[0])
    resume_text = extract_text_from_pdf(str(resume_path))
    if not resume_text:
        raise InputError(
            "Couldn't read any text from this PDF. If it's a scanned image, export your resume as a text PDF."
        )

    report(1, STEPS[1])
    jd = parse_jd(jd_text)

    report(2, STEPS[2])
    snippets, source = find_relevant_snippets(resume_text, jd_text)

    report(3, STEPS[3])
    recruiter = find_recruiter_email(recruiter_name, company_domain)

    report(4, STEPS[4])
    resume_header = " ".join(resume_text.split()[:40])  # usually holds your name and contact line
    subject, body = generate_cold_email(jd, snippets, recruiter_name, resume_header)

    return CopilotResult(jd, snippets, source, recruiter, subject, body)
