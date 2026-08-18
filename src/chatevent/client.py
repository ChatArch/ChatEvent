"""Small REST client for a running ChatEvent Event Hub."""

from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any


class ChatEventApiError(RuntimeError):
    """Raised when the ChatEvent REST API returns an HTTP or JSON error."""


@dataclass(frozen=True)
class ChatEventApiClient:
    """Thin client that maps Python calls to the public ChatEvent REST API."""

    base_url: str = "http://127.0.0.1:8765"
    timeout: float = 20.0

    def health(self) -> dict[str, Any]:
        return self._request("GET", "/api/health")

    def stats(self) -> dict[str, Any]:
        return self._request("GET", "/api/stats")

    def platforms(self) -> dict[str, Any]:
        return self._request("GET", "/api/platforms")

    def schema(self, kind: str) -> dict[str, Any]:
        return self._request("GET", f"/api/schema/{kind}")

    def list_subscriptions(self, *, enabled: bool | None = None) -> list[dict[str, Any]]:
        return self._request("GET", "/api/subscriptions", query={"enabled": enabled})

    def get_subscription(self, subscription_id: str) -> dict[str, Any]:
        return self._request(
            "GET",
            "/api/subscriptions/" + urllib.parse.quote(subscription_id, safe=""),
        )

    def save_subscription(self, path: Path) -> dict[str, Any]:
        payload = json.loads(path.read_text(encoding="utf-8"))
        return self._request("POST", "/api/subscriptions", payload=payload)

    def list_events(
        self,
        *,
        source: str | None = None,
        kind: str | None = None,
        subscription_id: str | None = None,
        q: str | None = None,
        since: str | None = None,
        days: str | None = None,
        from_: str | None = None,
        to: str | None = None,
        limit: int | None = None,
    ) -> dict[str, Any]:
        return self._request(
            "GET",
            "/api/events",
            query={
                "source": source,
                "kind": kind,
                "subscription_id": subscription_id,
                "q": q,
                "since": since,
                "days": days,
                "from": from_,
                "to": to,
                "limit": limit,
            },
        )

    def get_event(self, dedupe_key: str) -> dict[str, Any]:
        return self._request(
            "GET",
            "/api/events/" + urllib.parse.quote(dedupe_key, safe=""),
        )

    def record_json(self, path: Path) -> dict[str, Any]:
        payload = json.loads(path.read_text(encoding="utf-8"))
        return self._request("POST", "/api/events", payload=payload)

    def _request(
        self,
        method: str,
        path: str,
        *,
        query: dict[str, Any] | None = None,
        payload: Any | None = None,
    ) -> Any:
        url = _build_url(self.base_url, path, query=query)
        body = None
        headers = {"Accept": "application/json"}
        if payload is not None:
            body = json.dumps(payload).encode("utf-8")
            headers["Content-Type"] = "application/json"
        request = urllib.request.Request(url, data=body, headers=headers, method=method)
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                raw = response.read().decode("utf-8")
        except urllib.error.HTTPError as error:
            detail = error.read().decode("utf-8", errors="replace")
            raise ChatEventApiError(f"{error.code} {error.reason}: {detail}") from error
        except urllib.error.URLError as error:
            raise ChatEventApiError(str(error.reason)) from error
        if not raw:
            return None
        try:
            return json.loads(raw)
        except json.JSONDecodeError as error:
            raise ChatEventApiError(f"invalid JSON response from {url}: {error}") from error


def _build_url(
    base_url: str,
    path: str,
    *,
    query: dict[str, Any] | None = None,
) -> str:
    url = urllib.parse.urljoin(base_url.rstrip("/") + "/", path.lstrip("/"))
    clean_query = {
        key: value
        for key, value in (query or {}).items()
        if value is not None and value != ""
    }
    if clean_query:
        url += "?" + urllib.parse.urlencode(clean_query)
    return url
