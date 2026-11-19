import json
from datetime import datetime, timezone

import pytest
import requests

from pipeline.ingest import snapshot
from pipeline.locations import PILOT_LOCATIONS

LOCS = PILOT_LOCATIONS[:2]
RUN_AT = datetime(2026, 11, 6, 6, 17, tzinfo=timezone.utc)


class FakeResponse:
    def __init__(self, status_code, payload=None, text=""):
        self.status_code = status_code
        self._payload = payload
        self.text = text

    def json(self):
        if self._payload is None:
            raise ValueError("no json")
        return self._payload


class FakeSession:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def get(self, url, params=None, timeout=None):
        self.calls.append((url, params))
        r = self.responses.pop(0)
        if isinstance(r, Exception):
            raise r
        return r


def test_bmkg_one_request_per_location():
    session = FakeSession([FakeResponse(200, {"data": [i]}) for i in range(len(LOCS))])
    envs = snapshot.snapshot_bmkg(session, LOCS, delay_s=0)
    assert [c[1]["adm4"] for c in session.calls] == [loc.adm4 for loc in LOCS]
    assert [e["location"] for e in envs] == [loc.slug for loc in LOCS]
    assert all(e["error"] is None and e["status"] == 200 for e in envs)


def test_bmkg_failure_is_recorded_not_raised():
    session = FakeSession([requests.ConnectionError("down"), FakeResponse(200, {"data": []})])
    envs = snapshot.snapshot_bmkg(session, LOCS, delay_s=0)
    assert envs[0]["status"] is None and "ConnectionError" in envs[0]["error"]
    assert envs[1]["error"] is None


def test_non_json_response_is_an_error():
    session = FakeSession([FakeResponse(502, text="<html>bad gateway</html>")] * len(LOCS))
    envs = snapshot.snapshot_bmkg(session, LOCS, delay_s=0)
    assert envs[0]["status"] == 502 and "invalid JSON" in envs[0]["error"]


def test_openmeteo_single_call_split_per_location():
    payload = [{"latitude": loc.lat} for loc in LOCS]
    session = FakeSession([FakeResponse(200, payload)])
    envs = snapshot.snapshot_openmeteo(session, LOCS)
    assert len(session.calls) == 1
    assert [e["payload"]["latitude"] for e in envs] == [loc.lat for loc in LOCS]


def test_openmeteo_error_kept_for_every_location():
    err = {"error": True, "reason": "Cannot initialize WeatherVariable"}
    session = FakeSession([FakeResponse(400, err)])
    envs = snapshot.snapshot_openmeteo(session, LOCS)
    assert all(e["error"] == "HTTP 400" and e["payload"] == err for e in envs)


def test_openmeteo_location_count_mismatch_is_an_error():
    session = FakeSession([FakeResponse(200, [{"latitude": 0}])])
    envs = snapshot.snapshot_openmeteo(session, LOCS)
    assert all("expected 2 locations" in e["error"] for e in envs)


def test_write_layout_and_never_overwrite(tmp_path):
    env = snapshot._envelope("bmkg", "jakarta", "u", {}, RUN_AT, 200, {"x": 1}, None)
    [path] = snapshot.write([env], tmp_path, RUN_AT)
    assert path == tmp_path / "bmkg" / "2026-11-06" / "0617Z" / "jakarta.json"
    assert json.loads(path.read_text())["fetched_at"] == "2026-11-06T06:17:00Z"
    with pytest.raises(FileExistsError):
        snapshot.write([env], tmp_path, RUN_AT)


def test_main_rejects_unknown_source():
    with pytest.raises(SystemExit):
        snapshot.main(["--sources", "bmkg,usgs"])


def test_openmeteo_retries_once_after_network_error(monkeypatch):
    sleeps = []
    monkeypatch.setattr(snapshot.time, "sleep", sleeps.append)
    payload = [{"latitude": loc.lat} for loc in LOCS]
    session = FakeSession([requests.ReadTimeout("hang"), FakeResponse(200, payload)])
    envs = snapshot.snapshot_openmeteo(session, LOCS, retry_delay_s=5)
    assert len(session.calls) == 2 and sleeps == [5]
    assert all(e["error"] is None and e["status"] == 200 for e in envs)


def test_openmeteo_gives_up_after_second_network_error(monkeypatch):
    monkeypatch.setattr(snapshot.time, "sleep", lambda s: None)
    session = FakeSession([requests.ReadTimeout("hang"), requests.ReadTimeout("hang again")])
    envs = snapshot.snapshot_openmeteo(session, LOCS, retry_delay_s=5)
    assert len(session.calls) == 2
    assert all(e["status"] is None and "ReadTimeout" in e["error"] for e in envs)


def test_openmeteo_http_error_is_not_retried_again():
    # 429/5xx sudah di-retry oleh sesi HTTP; FakeSession akan IndexError kalau dipanggil dua kali.
    session = FakeSession([FakeResponse(503, {"error": True})])
    envs = snapshot.snapshot_openmeteo(session, LOCS, retry_delay_s=5)
    assert len(session.calls) == 1 and envs[0]["error"] == "HTTP 503"


def _fake_run(monkeypatch, tmp_path, bmkg_error, openmeteo_error):
    def fake(source, error):
        return lambda session, locs, *a, **k: [
            snapshot._envelope(source, loc.slug, "u", {}, RUN_AT, None if error else 200, None, error)
            for loc in LOCS
        ]

    monkeypatch.setattr(snapshot, "make_session", lambda: None)
    monkeypatch.setattr(snapshot, "snapshot_bmkg", fake("bmkg", bmkg_error))
    monkeypatch.setattr(snapshot, "snapshot_openmeteo", fake("open-meteo", openmeteo_error))
    return snapshot.main(["--out", str(tmp_path)])


def test_main_partial_failure_exits_zero_with_actions_warning(monkeypatch, tmp_path, capsys):
    monkeypatch.setenv("GITHUB_ACTIONS", "true")
    assert _fake_run(monkeypatch, tmp_path, None, "ReadTimeout: hang") == 0
    out = capsys.readouterr().out
    assert "::warning title=Snapshot open-meteo::2/2 lokasi gagal" in out
    assert "Snapshot bmkg" not in out
    assert len(list(tmp_path.rglob("*.json"))) == 2 * len(LOCS)


def test_main_total_failure_exits_one(monkeypatch, tmp_path):
    monkeypatch.delenv("GITHUB_ACTIONS", raising=False)
    assert _fake_run(monkeypatch, tmp_path, "ConnectionError: down", "ReadTimeout: hang") == 1


def test_main_all_ok_exits_zero(monkeypatch, tmp_path, capsys):
    monkeypatch.setenv("GITHUB_ACTIONS", "true")
    assert _fake_run(monkeypatch, tmp_path, None, None) == 0
    assert "::warning" not in capsys.readouterr().out
