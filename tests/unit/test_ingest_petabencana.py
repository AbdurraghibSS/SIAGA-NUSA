from datetime import date

import requests

from pipeline.ingest import petabencana as pb


class FakeResponse:
    def __init__(self, status, n):
        self.status_code, self.n = status, n

    def raise_for_status(self):
        if self.status_code != 200:
            raise requests.HTTPError(f"{self.status_code}")

    def json(self):
        return {"result": {"features": [{"i": i} for i in range(self.n)]}}


class FakeSession:
    def __init__(self, responses):
        self.responses, self.calls = list(responses), []

    def get(self, url, params=None, timeout=None):
        self.calls.append(params)
        return self.responses.pop(0)


def test_month_iteration_crosses_year():
    assert list(pb._month_starts(date(2024, 11, 1), date(2025, 2, 1))) == [
        date(2024, 11, 1), date(2024, 12, 1), date(2025, 1, 1), date(2025, 2, 1)]


def test_month_falls_back_to_weekly_windows(monkeypatch):
    monkeypatch.setattr(pb.time, "sleep", lambda s: None)
    session = FakeSession([FakeResponse(500, 0)] + [FakeResponse(200, 2)] * 5)
    features, mode = pb.fetch_month(session, date(2025, 4, 1))
    assert mode == "weekly" and len(features) == 10
    assert session.calls[1]["start"] == "2025-04-01T00:00:00+0700"
    assert session.calls[-1]["end"] == "2025-05-01T00:00:00+0700"
