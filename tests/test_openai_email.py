import httpx
import openai
import pytest

from src import config
from src.config import MissingKeyError
from src.openai_email import generate_cold_email, parse_jd


def test_parse_jd_reads_json_inside_a_code_block(fake_openai):
    fake_openai(['```json\n{"role_title": "Data Analyst", "company_name": "Acme", "location": "Dallas", "top_skills": ["SQL"]}\n```'])
    assert parse_jd("some job description") == {
        "role_title": "Data Analyst",
        "company_name": "Acme",
        "location": "Dallas",
        "top_skills": ["SQL"],
    }


def test_parse_jd_fills_in_missing_fields_and_splits_skill_strings(fake_openai):
    fake_openai([{"role_title": "Analyst", "top_skills": "SQL, Python , Excel"}])
    assert parse_jd("jd") == {"role_title": "Analyst", "company_name": "", "location": "", "top_skills": ["SQL", "Python", "Excel"]}


def test_parse_jd_survives_a_reply_that_is_not_json(fake_openai):
    fake_openai(["Sorry, I can't help with that."])
    assert parse_jd("jd")["role_title"] == ""


def test_parse_jd_skips_the_api_for_an_empty_description(fake_openai):
    client = fake_openai([])
    assert parse_jd("   ")["top_skills"] == []
    assert client.requests == []


def test_parse_jd_asks_for_json_with_the_configured_model(fake_openai, monkeypatch):
    monkeypatch.setattr(config, "OPENAI_MODEL", "test-model")
    client = fake_openai([{"role_title": "X"}])
    parse_jd("jd")
    assert client.requests[0]["model"] == "test-model"
    assert client.requests[0]["response_format"] == {"type": "json_object"}


def test_generate_email_returns_subject_and_body(fake_openai):
    client = fake_openai([{"subject": "Data Analyst role", "body": "Hi Sam,\n\nI built dashboards..."}])
    snippets = [{"text": "Built Power BI dashboards", "score": 0.9}]
    subject, body = generate_cold_email({"role_title": "Data Analyst", "company_name": "Acme"}, snippets, "Sam", "Jordan Patel")
    assert subject == "Data Analyst role"
    assert body.startswith("Hi Sam")
    prompt = client.requests[0]["messages"][1]["content"]
    assert "Built Power BI dashboards" in prompt and "Jordan Patel" in prompt and "Recruiter name: Sam" in prompt


def test_generate_email_uses_a_fallback_subject(fake_openai):
    fake_openai([{"body": "Hello"}])
    subject, body = generate_cold_email({"role_title": "Data Analyst"}, [], "")
    assert subject == "Interest in the Data Analyst role"
    assert body == "Hello"


def test_retries_without_temperature_for_models_that_reject_it(fake_openai):
    request = httpx.Request("POST", "https://api.openai.com/v1/chat/completions")
    error = openai.BadRequestError(
        "Unsupported value: 'temperature' does not support 0.2",
        response=httpx.Response(400, request=request),
        body=None,
    )
    client = fake_openai([error, {"role_title": "Analyst"}])
    assert parse_jd("jd")["role_title"] == "Analyst"
    assert "temperature" in client.requests[0] and "temperature" not in client.requests[1]


def test_missing_openai_key_gives_a_clear_error():
    config.get_openai_client.cache_clear()
    with pytest.raises(MissingKeyError, match="OPENAI_API_KEY"):
        parse_jd("a real job description")
