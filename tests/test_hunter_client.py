from unittest import mock

import pytest

from src import config, hunter_client
from src.hunter_client import clean_domain, find_recruiter_email


def response(status, payload):
    resp = mock.MagicMock(status_code=status, reason="Error")
    resp.json.return_value = payload
    return resp


@pytest.fixture
def hunter_on(monkeypatch):
    monkeypatch.setattr(config, "HUNTER_API_KEY", "test-key")


def test_no_key_means_no_lookup():
    with mock.patch.object(hunter_client.requests, "get") as get:
        result = find_recruiter_email("Natalya Lowe", "acme.com")
    assert result.email is None and "isn't set up" in result.message
    get.assert_not_called()


@pytest.mark.parametrize(
    "raw, expected",
    [("acme.com", "acme.com"), ("https://www.acme.com/careers?x=1", "acme.com"), (" WWW.Acme.COM ", "acme.com"), ("http://jobs.acme.co.uk/", "jobs.acme.co.uk")],
)
def test_clean_domain(raw, expected):
    assert clean_domain(raw) == expected


def test_email_finder_result_is_used(hunter_on):
    with mock.patch.object(hunter_client.requests, "get", return_value=response(200, {"data": {"email": "n.lowe@acme.com", "score": 91}})) as get:
        result = find_recruiter_email("Natalya Lowe", "https://www.acme.com")
    assert (result.email, result.source, result.confidence) == ("n.lowe@acme.com", "Email Finder", 91)
    params = get.call_args.kwargs["params"]
    assert params["domain"] == "acme.com" and params["first_name"] == "Natalya" and params["last_name"] == "Lowe"


def test_domain_search_exact_name_match(hunter_on):
    replies = [
        response(200, {"data": {"email": None}}),
        response(200, {"data": {"emails": [
            {"first_name": "Chris", "last_name": "Boss", "value": "chris@acme.com"},
            {"first_name": "natalya", "last_name": "LOWE", "value": "natalya@acme.com", "confidence": 80},
        ]}}),
    ]
    with mock.patch.object(hunter_client.requests, "get", side_effect=replies):
        result = find_recruiter_email("Natalya Lowe", "acme.com")
    assert (result.email, result.source) == ("natalya@acme.com", "Domain Search")


def test_never_returns_someone_elses_email(hunter_on):
    replies = [
        response(200, {"data": {"email": None}}),
        response(200, {"data": {"emails": [{"first_name": "Chris", "last_name": "Boss", "value": "chris@acme.com"}]}}),
    ]
    with mock.patch.object(hunter_client.requests, "get", side_effect=replies):
        result = find_recruiter_email("Natalya Lowe", "acme.com")
    assert result.email is None
    assert "couldn't find Natalya Lowe" in result.message


def test_bad_key_stops_early_with_a_clear_message(hunter_on):
    with mock.patch.object(hunter_client.requests, "get", return_value=response(401, {"errors": [{"details": "No user found for the API key supplied"}]})) as get:
        result = find_recruiter_email("Natalya Lowe", "acme.com")
    assert result.email is None and "401" in result.message and "API key" in result.message
    assert get.call_count == 1


def test_missing_name_or_domain(hunter_on):
    assert find_recruiter_email("", "acme.com").email is None
    assert find_recruiter_email("Natalya Lowe", "").email is None
