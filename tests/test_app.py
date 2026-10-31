from unittest import mock

import gradio as gr
import pytest

from src import app_gradio, config, n8n_client
from src.hunter_client import RecruiterEmail
from src.pipeline import CopilotResult

from .conftest import SAMPLE_JD, SAMPLE_RESUME_LINES, make_pdf


def test_app_builds():
    assert isinstance(app_gradio.demo, gr.Blocks)


def test_word_count_flags_emails_outside_the_target():
    assert "0 words" in app_gradio.word_count_html("")
    assert "off" not in app_gradio.word_count_html("word " * 150)
    assert "off" in app_gradio.word_count_html("word " * 40)


def test_refresh_draft_keeps_gmail_link_in_step_with_edits():
    button, count = app_gradio.refresh_draft("a@b.com", "Hi", "Hello there")
    assert "to=a%40b.com" in button.link and "body=Hello%20there" in button.link
    assert button.interactive is True
    assert "2 words" in count
    empty_button, _ = app_gradio.refresh_draft("", "", "")
    assert empty_button.interactive is False


def test_match_panel_escapes_text_and_shows_matches():
    result = CopilotResult(
        jd={"role_title": "<b>Analyst</b>", "company_name": "Acme", "location": "", "top_skills": ["SQL"]},
        snippets=[{"text": f"line {i}", "score": 0.9 - i / 10} for i in range(5)],
        search_source="pinecone",
        recruiter=RecruiterEmail(None),
        subject="s",
        body="b",
    )
    html = app_gradio.match_html(result)
    assert "&lt;b&gt;Analyst&lt;/b&gt;" in html and "<b>Analyst</b>" not in html
    assert "Show 2 more" in html and "Pinecone" in html


def test_write_email_turns_input_problems_into_friendly_errors():
    with pytest.raises(gr.Error, match="Upload your resume"):
        app_gradio.write_email(None, SAMPLE_JD, "", "", progress=lambda *a, **k: None)


def test_write_email_end_to_end(tmp_path, fake_models, fake_openai, monkeypatch):
    fake_openai([
        {"role_title": "Data Analyst", "company_name": "Northwind", "location": "Dallas", "top_skills": ["SQL"]},
        {"subject": "Hello", "body": "Hi Natalya"},
    ])
    resume = make_pdf(tmp_path / "resume.pdf", SAMPLE_RESUME_LINES)
    match, to, note, subject, body, status, meta = app_gradio.write_email(
        str(resume), SAMPLE_JD, "Natalya Lowe", "northwind.com", progress=lambda *a, **k: None
    )
    assert "Data Analyst" in match and subject == "Hello" and body == "Hi Natalya"
    assert to == "" and "Hunter isn&#x27;t set up" in note
    assert meta == {"job_title": "Data Analyst", "company": "Northwind"}


def test_send_checks_setup_and_inputs(monkeypatch):
    assert "isn't set up" in n8n_client.send_via_n8n("a@b.com", "s", "b")
    monkeypatch.setattr(config, "N8N_WEBHOOK_URL", "https://n8n.example/webhook")
    assert "recruiter's email" in n8n_client.send_via_n8n("", "s", "b")
    assert "can't be empty" in n8n_client.send_via_n8n("a@b.com", "", "b")


def test_send_posts_the_email_to_n8n(monkeypatch):
    monkeypatch.setattr(config, "N8N_WEBHOOK_URL", "https://n8n.example/webhook")
    with mock.patch.object(n8n_client.requests, "post", return_value=mock.MagicMock(status_code=200)) as post:
        html = app_gradio.send_email("a@b.com", "Subject", "Body", {"job_title": "Analyst", "company": "Acme"})
    assert "Sent to a@b.com" in html
    payload = post.call_args.kwargs["json"]
    assert payload == {"to": "a@b.com", "subject": "Subject", "body": "Body", "job_title": "Analyst", "company": "Acme", "jd_url": ""}
