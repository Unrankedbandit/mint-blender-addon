"""HTTP client for the Mint Blender API."""

from __future__ import annotations

import json
import urllib.parse
import urllib.error
import urllib.request
from typing import Any, Callable, Dict, Optional

from .config import MintBlenderConfig
from .http import urlopen_with_config

UrlOpen = Callable[..., Any]


class MintApiError(RuntimeError):
    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status = status


class MintBlenderClient:
    def __init__(
        self,
        config: MintBlenderConfig,
        urlopen: Optional[UrlOpen] = None,
        timeout_seconds: int = 30,
    ):
        self.config = config
        self.urlopen = urlopen
        self.timeout_seconds = timeout_seconds

    def _url(self, path: str, params: Optional[Dict[str, Any]] = None) -> str:
        url = "%s/%s" % (self.config.api_base_url.rstrip("/"), path.lstrip("/"))
        query = {
            key: value
            for key, value in (params or {}).items()
            if value is not None
        }
        if query:
            url = "%s?%s" % (url, urllib.parse.urlencode(query))
        return url

    def _get(
        self,
        path: str,
        access_token: str,
        params: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        request = urllib.request.Request(
            self._url(path, params),
            headers={
                "Authorization": "Bearer %s" % access_token,
                "Accept": "application/json",
                "User-Agent": "MintBlenderAssetBrowser/0.1.0",
            },
            method="GET",
        )
        try:
            response = urlopen_with_config(
                request,
                self.config,
                self.urlopen,
                timeout=self.timeout_seconds,
            )
        except urllib.error.HTTPError as error:
            raise self._api_error_from_response(error) from error
        status = getattr(response, "status", 200)
        body = response.read().decode("utf-8")
        data = json.loads(body) if body else {}
        if status >= 400:
            detail = data.get("detail") if isinstance(data, dict) else None
            raise MintApiError(status, detail or "Mint API request failed")
        if not isinstance(data, dict):
            raise MintApiError(status, "Mint API returned an unexpected response")
        return data

    def _post(
        self,
        path: str,
        access_token: str,
        body: Optional[Dict[str, Any]] = None,
        timeout_seconds: Optional[int] = None,
    ) -> Dict[str, Any]:
        request = urllib.request.Request(
            self._url(path),
            data=json.dumps(body or {}).encode("utf-8"),
            headers={
                "Authorization": "Bearer %s" % access_token,
                "Accept": "application/json",
                "Content-Type": "application/json",
                "User-Agent": "MintBlenderAssetBrowser/0.1.0",
            },
            method="POST",
        )
        try:
            response = urlopen_with_config(
                request,
                self.config,
                self.urlopen,
                timeout=timeout_seconds or self.timeout_seconds,
            )
        except urllib.error.HTTPError as error:
            raise self._api_error_from_response(error) from error
        status = getattr(response, "status", 200)
        raw_body = response.read().decode("utf-8")
        data = json.loads(raw_body) if raw_body else {}
        if status >= 400:
            detail = data.get("detail") if isinstance(data, dict) else None
            raise MintApiError(status, detail or "Mint API request failed")
        if not isinstance(data, dict):
            raise MintApiError(status, "Mint API returned an unexpected response")
        return data

    def _api_error_from_response(self, response: Any) -> MintApiError:
        status = int(getattr(response, "code", getattr(response, "status", 500)))
        body = response.read().decode("utf-8")
        try:
            data = json.loads(body) if body else {}
        except json.JSONDecodeError:
            data = {}
        detail = data.get("detail") if isinstance(data, dict) else None
        title = data.get("title") if isinstance(data, dict) else None
        return MintApiError(status, detail or title or "Mint API request failed")

    def me(self, access_token: str) -> Dict[str, Any]:
        return self._get("me", access_token)

    def list_models(
        self,
        access_token: str,
        limit: int = 50,
        cursor: Optional[str] = None,
    ) -> Dict[str, Any]:
        return self._get(
            "models",
            access_token,
            {"limit": limit, "cursor": cursor},
        )

    def list_worlds(
        self,
        access_token: str,
        limit: int = 50,
        cursor: Optional[str] = None,
    ) -> Dict[str, Any]:
        return self._get(
            "worlds",
            access_token,
            {"limit": limit, "cursor": cursor},
        )

    def list_packs(
        self,
        access_token: str,
        limit: int = 50,
        cursor: Optional[str] = None,
    ) -> Dict[str, Any]:
        return self._get(
            "packs",
            access_token,
            {"limit": limit, "cursor": cursor},
        )

    def get_model(self, access_token: str, model_id: str) -> Dict[str, Any]:
        return self._get("models/%s" % urllib.parse.quote(model_id, safe=""), access_token)

    def get_world(self, access_token: str, world_id: str) -> Dict[str, Any]:
        return self._get("worlds/%s" % urllib.parse.quote(world_id, safe=""), access_token)

    def export_world_ply(self, access_token: str, world_id: str) -> Dict[str, Any]:
        quoted_world_id = urllib.parse.quote(world_id, safe="")
        return self._post(
            "worlds/%s/exports/ply" % quoted_world_id,
            access_token,
            timeout_seconds=600,
        )
