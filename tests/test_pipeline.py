import urllib.parse

import pytest

from src.pipeline import STEPS, InputError, build_gmail_link, run_pipeline

from .conftest import SAMPLE_JD, SAMPLE_RESUME_LINES, make_pdf

JD_REPLY = {"role_title": "Data Analyst", "company_name": "Northwind Logistics", "location": "Dallas", "top_skills": ["SQL", "Power BI"]}
EMAIL_REPLY = {"subject": "Data Analyst at Northwind", "body": "Hi Natalya,\n\nI built SQL pipelines...\n\nBest,\nJordan Patel"}


def test_full_run_with_a_real_pdf(tmp_path, fake_models, fake_openai):
    client = fake_openai([JD_REPLY, EMAIL_REPLY])
    resume = make_pdf(tmp_path / "resume.pdf", SAMPLE_RESUME_LINES)
    steps_seen = []

    result = run_pipeline(str(resume), SAMPLE_JD, "Natalya Lowe", "northwind.com", lambda i, label: steps_seen.append(label))

    assert steps_seen == STEPS
    assert result.jd["company_name"] == "Northwind Logistics"
    assert result.subject == "Data Analyst at Northwind"
    assert result.snippets and result.search_source == "in-memory"
    assert result.recruiter.email is None  # Hunter isn't set up in tests
    email_prompt = client.requests[1]["messages"][1]["content"]
    assert "Jordan Patel" in email_prompt  # resume header is passed for the sign-off


def test_needs_a_resume():
    with pytest.raises(InputError, match="Upload your resume"):
        run_pipeline(None, SAMPLE_JD)


def test_resume_must_be_a_pdf(tmp_path):
    doc = tmp_path / "resume.docx"
    doc.write_text("hi")
    with pytest.raises(InputError, match="PDF"):
        run_pipeline(str(doc), SAMPLE_JD)


def test_job_description_must_not_be_too_short(tmp_path):
    resume = make_pdf(tmp_path / "resume.pdf", SAMPLE_RESUME_LINES)
    with pytest.raises(InputError, match="full job description"):
        run_pipeline(str(resume), "Data analyst, Dallas")


def test_pdf_with_no_text(tmp_path):
    resume = make_pdf(tmp_path / "scan.pdf", [])
    with pytest.raises(InputError, match="scanned image"):
        run_pipeline(str(resume), SAMPLE_JD)


def test_gmail_link_carries_everything_safely():
    link = build_gmail_link("a@b.com", "Hello & welcome", "Line 1\nLine 2 #50% off?")
    params = urllib.parse.parse_qs(urllib.parse.urlparse(link).query)
    assert params["to"] == ["a@b.com"]
    assert params["su"] == ["Hello & welcome"]
    assert params["body"] == ["Line 1\nLine 2 #50% off?"]
    assert link.startswith("https://mail.google.com/mail/?view=cm&fs=1&")
