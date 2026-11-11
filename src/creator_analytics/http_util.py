"""HTTP helper that strips secrets out of error text."""

from __future__ import annotations

import requests

USER_AGENT = "SocialMediaDataAnalysis/1.0 (creator dashboard; public metrics only)"


class APIError(Exception):
    """A request failed. The message has already had secrets removed."""


def redact(text: str, secrets: list[str]) -> str:
    cleaned = text
    for secret in secrets:
        if secret:
            cleaned = cleaned.replace(secret, "[redacted]")
    return cleaned


def request_json(
    session,
    method: str,
    url: str,
    *,
    params: dict | None = None,
    json_body: dict | None = None,
    form_body: dict | None = None,
    headers: dict | None = None,
    secrets: list[str] | None = None,
    timeout: int = 25,
) -> dict:
    secret_values = [item for item in (secrets or []) if item]
    merged_headers = {"User-Agent": USER_AGENT, **(headers or {})}
    request_kwargs = {"params": params, "headers": merged_headers, "timeout": timeout}
    if form_body is not None:
        request_kwargs["data"] = form_body
    if json_body is not None:
        request_kwargs["json"] = json_body
    try:
        response = session.request(method, url, **request_kwargs)
    except requests.RequestException as exc:
        raise APIError(redact(str(exc), secret_values)) from None
    if response.status_code >= 400:
        body = redact(response.text[:500], secret_values)
        safe_url = redact(url, secret_values)
        raise APIError(f"{response.status_code} from {safe_url}: {body}")
    try:
        payload = response.json()
    except ValueError:
        raise APIError(f"Response from {redact(url, secret_values)} was not JSON") from None
    if not isinstance(payload, dict):
        raise APIError(f"Response from {redact(url, secret_values)} was not a JSON object")
    return payload


def safe_int(value) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
