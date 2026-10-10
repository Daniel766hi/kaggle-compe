import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

USER_AGENT = "kaggle-dataset-pipeline/1.0 (+https://github.com/daniel766hi/kaggle-compe)"
TIMEOUT_S = 90


def make_session(retry_statuses=(429, 500, 502, 503, 504)):
    session = requests.Session()
    retry = Retry(
        total=5,
        backoff_factor=2,
        status_forcelist=retry_statuses,
        allowed_methods=("GET",),
        raise_on_status=False,
    )
    session.mount("https://", HTTPAdapter(max_retries=retry))
    session.headers["User-Agent"] = USER_AGENT
    return session


def get_json(session, url, params=None):
    resp = session.get(url, params=params, timeout=TIMEOUT_S)
    resp.raise_for_status()
    return resp.json()
