"""HTTP view exposing a WAF-safe proxy to the mobilites-m OTP2 API.

Mounted at ``/otp_proxy_m/{key}/{tail}`` where ``key`` is the route key
chosen when configuring the entry (default ``m``). Clients point their OTP2
base URL at e.g. ``http://127.0.0.1:8123/otp_proxy_m/m/otp/routers/default``.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from dataclasses import dataclass, field
from http import HTTPStatus
from typing import Any

from aiohttp import ClientError, web
from homeassistant.components.http import HomeAssistantView
from homeassistant.core import HomeAssistant

from .const import DOMAIN, GRAPHQL_PATH, INDEX_PATH, REQUEST_TIMEOUT
from .rewrite import RewriteError, reshape_response, rewrite_payload

_LOGGER = logging.getLogger(__name__)

GRAPHQL_CONTENT_TYPE = "application/graphql"

# Headers forwarded to the upstream OTP2 server.
FORWARD_HEADERS = ("accept", "x-api-key", "user-agent")


@dataclass
class ProxyStats:
    """Runtime counters exposed by the status sensor."""

    requests_total: int = 0
    rewrites_total: int = 0
    errors_total: int = 0
    upstream_403_total: int = 0
    last_error: str | None = None
    last_request_at: float | None = None
    last_success_at: float | None = None


@dataclass
class ProxyRuntime:
    """State of one configured entry."""

    session: Any
    upstream: str
    stats: ProxyStats = field(default_factory=ProxyStats)

    @property
    def upstream_base(self) -> str:
        return self.upstream.rstrip("/")


class OtpProxyView(HomeAssistantView):
    """Reverse proxy that neutralises the mobilites-m WAF rule."""

    url = "/otp_proxy_m/{key}/{tail:.*}"
    name = "api:otp_proxy_m"
    requires_auth = False
    allowed_methods = ["GET", "POST"]

    def __init__(self) -> None:
        self._runtimes: dict[str, ProxyRuntime] = {}

    def register_runtime(self, key: str, runtime: ProxyRuntime) -> None:
        self._runtimes[key] = runtime

    def unregister_runtime(self, key: str) -> None:
        self._runtimes.pop(key, None)

    async def get(self, request: web.Request, key: str, tail: str = ""):
        return await self._handle(request, key, tail)

    async def post(self, request: web.Request, key: str, tail: str = ""):
        return await self._handle(request, key, tail)

    async def _handle(self, request: web.Request, key: str, tail: str) -> web.Response:
        runtime = self._runtimes.get(key)
        if runtime is None:
            return self._json_error("unknown proxy route", HTTPStatus.NOT_FOUND)

        stats = runtime.stats
        stats.requests_total += 1
        stats.last_request_at = time.time()

        path = f"/{tail}" if tail else ""
        if path == INDEX_PATH and request.method == "GET":
            # Emulated index endpoint: the public server answers 404 here but
            # the openpublictransport config flow health-checks this path.
            stats.last_success_at = time.time()
            return web.json_response(
                {
                    "serverInfo": {
                        "name": "otp-proxy-m",
                        "otpVersion": "2.7.0",
                        "upstream": runtime.upstream_base,
                    }
                }
            )

        if path.endswith(GRAPHQL_PATH) and request.method == "POST":
            return await self._graphql(request, runtime, path)

        return await self._forward(request, runtime, path)

    async def _graphql(self, request: web.Request, runtime: ProxyRuntime, path: str) -> web.Response:
        stats = runtime.stats
        body = await request.read()
        rewritten = False

        if request.content_type.startswith(GRAPHQL_CONTENT_TYPE):
            # The WAF does not inspect this content type; forward verbatim.
            return await self._forward(
                request, runtime, path, data=body, content_type=GRAPHQL_CONTENT_TYPE
            )

        try:
            payload, rewritten = rewrite_payload(body.decode("utf-8", errors="replace"))
        except RewriteError as err:
            stats.errors_total += 1
            stats.last_error = f"rewrite failed: {err}"
            _LOGGER.warning("otp_proxy_m: %s", stats.last_error)
            return self._json_error(str(err), HTTPStatus.BAD_REQUEST)

        if rewritten:
            stats.rewrites_total += 1
        return await self._forward(
            request,
            runtime,
            path,
            data=json.dumps(payload or {}).encode(),
            content_type="application/json",
            rewritten=rewritten,
        )

    async def _forward(
        self,
        request: web.Request,
        runtime: ProxyRuntime,
        path: str,
        data: bytes | None = None,
        content_type: str | None = None,
        rewritten: bool = False,
    ) -> web.Response:
        stats = runtime.stats
        url = f"{runtime.upstream_base}{path}"
        if request.query_string:
            url = f"{url}?{request.query_string}"
        headers = {
            k: v for k, v in request.headers.items() if k.lower() in FORWARD_HEADERS
        }
        if content_type:
            headers["Content-Type"] = content_type

        try:
            async with asyncio.timeout(REQUEST_TIMEOUT):
                resp = await runtime.session.request(
                    request.method, url, data=data, headers=headers
                )
                raw = await resp.read()
        except (TimeoutError, asyncio.TimeoutError):
            stats.errors_total += 1
            stats.last_error = f"upstream timeout: {url}"
            return self._json_error("upstream timeout", HTTPStatus.GATEWAY_TIMEOUT)
        except ClientError as err:
            stats.errors_total += 1
            stats.last_error = f"upstream connection error: {err}"
            return self._json_error("upstream connection error", HTTPStatus.BAD_GATEWAY)

        if resp.status == HTTPStatus.FORBIDDEN:
            stats.upstream_403_total += 1
            stats.errors_total += 1
            stats.last_error = f"upstream forbidden (WAF?): {url}"
            _LOGGER.warning("otp_proxy_m: %s", stats.last_error)
            return self._json_error("upstream forbidden", HTTPStatus.BAD_GATEWAY)

        content = raw
        ctype = resp.headers.get("Content-Type", "application/octet-stream")
        if rewritten and "json" in ctype:
            content = self._reshaped(raw)

        if resp.status == HTTPStatus.OK:
            stats.last_success_at = time.time()

        return web.Response(body=content, status=resp.status, content_type=ctype)

    @staticmethod
    def _reshaped(raw: bytes) -> bytes:
        try:
            decoded = json.loads(raw)
        except (ValueError, TypeError):
            return raw
        if isinstance(decoded, dict) and isinstance(decoded.get("data"), dict):
            decoded["data"] = reshape_response(decoded["data"])
        return json.dumps(decoded, separators=(",", ":")).encode()

    @staticmethod
    def _json_error(message: str, status: HTTPStatus) -> web.Response:
        return web.json_response({"error": message}, status=status)


def get_or_create_view(hass: HomeAssistant) -> OtpProxyView:
    """Return the shared proxy view, registering it on first use."""
    store = hass.data.setdefault(DOMAIN, {})
    view: OtpProxyView | None = store.get("view")
    if view is None:
        view = OtpProxyView()
        hass.http.register_view(view)
        store["view"] = view
    return view
