import time
import types

from scraper.jira_client import JiraScraper, JiraClientError


class MockResp:
    def __init__(self, status_code=200, json_data=None, headers=None, text=''):
        self.status_code = status_code
        self._json = json_data or {}
        self.headers = headers or {}
        self.text = text

    def json(self):
        return self._json


def test_request_handles_429_then_success(monkeypatch):
    seq = [
        MockResp(status_code=429, json_data={}, headers={"Retry-After": "0"}, text=''),
        MockResp(status_code=200, json_data={"ok": True}),
    ]

    def fake_get(url, params=None):
        return seq.pop(0)

    s = JiraScraper(timeout=1, max_retries=3, backoff_factor=0)
    monkeypatch.setattr(s.client, 'get', fake_get)
    out = s._request('http://example.com', params={})
    assert out == {"ok": True}


def test_request_handles_5xx_then_fail(monkeypatch):
    seq = [
        MockResp(status_code=500, json_data={}, headers={}, text='err'),
        MockResp(status_code=500, json_data={}, headers={}, text='err'),
    ]

    def fake_get(url, params=None):
        return seq.pop(0)

    s = JiraScraper(timeout=1, max_retries=2, backoff_factor=0)
    monkeypatch.setattr(s.client, 'get', fake_get)
    try:
        s._request('http://example.com', params={})
        assert False, "Expected JiraClientError"
    except JiraClientError:
        assert True
