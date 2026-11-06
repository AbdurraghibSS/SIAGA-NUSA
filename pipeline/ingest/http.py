"""Sesi HTTP bersama: retry untuk 429/5xx dan User-Agent yang jelas."""

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

USER_AGENT = "SIAGA-NUSA/0.1 (+https://github.com/AbdurraghibSS/SIAGA-NUSA)"
TIMEOUT_S = 30


def make_session() -> requests.Session:
    retry = Retry(
        total=3,
        backoff_factor=2,
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=("GET",),
        raise_on_status=False,  # simpan status akhir (mis. 500) di envelope
    )
    session = requests.Session()
    session.headers["User-Agent"] = USER_AGENT
    session.mount("https://", HTTPAdapter(max_retries=retry))
    return session
