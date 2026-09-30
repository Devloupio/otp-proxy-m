"""Realtime enrichment from the mobilites-m legacy OTP1 REST API.

The OTP2 GraphQL endpoint of the M network (otp.mobilites-m.fr) has no
GTFS-RT updaters: stoptimes arrive as ``realtime: false, delay 0``. The
legacy REST proxy ``data.mobilites-m.fr`` exposes the *same* OTP feeds with
live data (realtimeState UPDATED, occupancy...) but requires the
``origin`` header.

Enrichment strategy (departures only):
- batch-fetch ``GET .../index/stops/{stopId}/stoptimes`` for every stop id
  seen in the query,
- match ``times[].tripId`` against GraphQL ``trip.gtfsId`` (byte-identical),
- patch ``realtime / realtimeDeparture / departureDelay`` (+ occupancy).

planConnection legs carry no reliable realtime in the legacy planner
(realTime: false) so trips stay unenriched.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Any

_LOGGER = logging.getLogger(__name__)

ORIGIN_HEADER = "mon_appli"

REST_BASE = "https://data.mobilites-m.fr"
STOPTIMES_URL = REST_BASE + "/api/routers/default/index/stops/{stop_id}/stoptimes"

_REST_TIMEOUT = 12

_STOPTIMES_Q = re.compile(r"\bstoptimesWithoutPatterns\b")
_STOPS_IDS_Q = re.compile(r"stops\s*\(\s*ids\s*:\s*\[([^\]]*)\]")


def is_enrichable(query: str) -> bool:
    """True when the GraphQL query fetches stoptimes (enrichable)."""
    return bool(_STOPTIMES_Q.search(query))


def extract_stop_ids(query: str) -> list[str]:
    """Extract every stop id from ``stops(ids: ["A", "B"])`` in the query."""
    ids: list[str] = []
    for m in _STOPS_IDS_Q.finditer(query):
        ids.extend(re.findall(r'"([^"]+)"', m.group(1)))
    seen: set[str] = set()
    return [i for i in ids if not (i in seen or seen.add(i))]


@dataclass
class LiveTimes:
    """Parsed REST stoptimes for one stop, keyed by (serviceDay, tripId)."""

    by_trip: dict[tuple[int, str], dict[str, Any]]

    def __bool__(self) -> bool:
        return bool(self.by_trip)

    def __eq__(self, other: object) -> bool:
        return isinstance(other, LiveTimes) and self.by_trip == other.by_trip

    @classmethod
    def parse(cls, payload: Any) -> LiveTimes:
        by: dict[tuple[int, str], dict[str, Any]] = {}
        if not isinstance(payload, list):
            return cls({})
        for pattern in payload:
            if not isinstance(pattern, dict):
                continue
            for t in pattern.get("times") or []:
                trip_id = t.get("tripId")
                service_day = t.get("serviceDay")
                if not trip_id or service_day is None:
                    continue
                try:
                    key = (int(service_day), str(trip_id))
                except (TypeError, ValueError):
                    continue
                by[key] = t
        return cls(by)


def build_headers(origin: str = ORIGIN_HEADER) -> dict[str, str]:
    return {"origin": origin, "Accept": "application/json"}


def _patch_one_stop(stop: dict[str, Any], live: LiveTimes) -> dict[str, Any]:
    """Patch stoptimes of a single (merged) stop object."""
    stms = stop.get("stoptimesWithoutPatterns")
    if not isinstance(stms, list):
        return stop
    out: list[dict[str, Any]] = []
    for stm in stms:
        if not isinstance(stm, dict):
            out.append(stm)
            continue
        trip = stm.get("trip") or {}
        row = live.by_trip.get(
            (int(stm.get("serviceDay", 0)), str(trip.get("gtfsId", "")))
        )
        if row is None:
            out.append(stm)
            continue
        stm = dict(stm)
        if row.get("realtime"):
            stm["realtime"] = True
            stm["realtimeState"] = row.get("realtimeState", "UPDATED")
            if row.get("realtimeDeparture") is not None:
                stm["realtimeDeparture"] = int(row["realtimeDeparture"])
            if row.get("departureDelay") is not None:
                stm["departureDelay"] = int(row["departureDelay"])
            if row.get("occupancy"):
                stm["occupancy"] = row["occupancy"]
        out.append(stm)
    stop = dict(stop)
    stop["stoptimesWithoutPatterns"] = out
    return stop


def patch_data(data: dict[str, Any], live_by_stop: dict[str, LiveTimes]) -> dict[str, Any]:
    """Patch a GraphQL ``data`` dict (returns a patched copy).

    Handles both shapes:
    - raw upstream: ``{"stops": [...]}`` and the aliased ``{"stop": [...]}``,
    - already-reshaped: ``{"stop": {...}}`` (object).
    Unknown/gone stops are left untouched.
    """
    patched = dict(data)

    def patch_stop(s: Any) -> Any:
        if isinstance(s, dict):
            live = live_by_stop.get(s.get("gtfsId", ""))
            if live is not None:
                return _patch_one_stop(s, live)
        return s

    stop_alias = data.get("stop")
    if isinstance(stop_alias, list):
        patched["stop"] = [patch_stop(s) for s in stop_alias]
    elif isinstance(stop_alias, dict):
        patched["stop"] = patch_stop(stop_alias)
    if isinstance(data.get("stops"), list):
        patched["stops"] = [patch_stop(s) for s in patched["stops"]]
    return patched


async def fetch_live_times(
    session: Any, stop_id: str, origin: str = ORIGIN_HEADER
) -> LiveTimes | None:
    """Fetch+parse REST stoptimes for one stop using an existing aiohttp session."""
    import asyncio
    import json as _json

    url = STOPTIMES_URL.format(stop_id=stop_id)
    try:
        async with asyncio.timeout(_REST_TIMEOUT):
            resp = await session.get(url, headers=build_headers(origin))
            if resp.status not in (200, 204):
                _LOGGER.debug("otp_proxy_m realtime: HTTP %s for %s", resp.status, url)
                return None
            payload = await resp.read()
    except TimeoutError:
        _LOGGER.warning("otp_proxy_m realtime: timeout fetching %s", url)
        return None
    except Exception as err:  # aiohttp.ClientError & co
        _LOGGER.warning("otp_proxy_m realtime: error fetching %s: %s", url, err)
        return None
    try:
        return LiveTimes.parse(_json.loads(payload))
    except ValueError:
        return None
