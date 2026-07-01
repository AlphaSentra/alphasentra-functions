import uuid

import requests


class EToroAuthError(Exception):
    pass


def public_api_session(api_key: str, user_key: str, *, timeout: int = 30) -> requests.Session:
    session = requests.Session()
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (compatible; alphasentra-etoro-client)",
        "Accept": "application/json",
        "x-api-key": api_key,
        "x-user-key": user_key,
        "x-request-id": str(uuid.uuid4()),
    })
    return session
