"""The OTP Proxy M integration.

Sets up an unauthenticated HTTP view that proxies requests to the
mobilites-m OTP2 server, rewriting WAF-blocked GraphQL payloads.
Also repairs openpublictransport trip entries missing otp_base_url
(upstream bug: URL only persisted when an API key is set).
"""

from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import CONF_UPSTREAM, DEFAULT_UPSTREAM, DOMAIN
from .http import ProxyRuntime, get_or_create_view

_LOGGER = logging.getLogger(__name__)

PLATFORMS = ["sensor"]

OPT_DOMAIN = "openpublictransport"
OPT_BASE_URL = "otp_base_url"


async def _repair_trip_entries(hass: HomeAssistant) -> list[str]:
    """Add otp_base_url to openpublictransport entries that miss it.

    Works around the openpublictransport config-flow bug where trip entries
    without an API key are stored without their base URL.
    Returns the list of repaired entry ids.
    """
    repaired: list[str] = []
    for entry in hass.config_entries.async_entries(OPT_DOMAIN):
        data = entry.data
        if OPT_BASE_URL in data or not data.get("is_trip"):
            continue
        # point on our proxy using the shared default route key
        proxy_route = _first_route_key(hass)
        url = f"http://127.0.0.1:8123/otp_proxy_m/{proxy_route}/otp/routers/default"
        new_data = {**data, OPT_BASE_URL: url}
        hass.config_entries.async_update_entry(entry, data=new_data)
        repaired.append(entry.entry_id)
        _LOGGER.warning(
            "otp_proxy_m: repaired openpublictransport trip entry %s with %s",
            entry.title,
            url,
        )
    if repaired:
        for entry_id in repaired:
            await hass.config_entries.async_reload(entry_id)
    return repaired


def _first_route_key(hass: HomeAssistant) -> str:
    store = hass.data.get(DOMAIN, {})
    for entry_id, data in store.items():
        if entry_id == "view":
            continue
        runtime = data.get("runtime") if isinstance(data, dict) else None
        if runtime is not None:
            for key, rt in getattr(data["view"], "_runtimes", {}).items():
                if rt is runtime:
                    return key
    return "m"


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Register the proxy route for this entry."""
    store = hass.data.setdefault(DOMAIN, {})
    view = get_or_create_view(hass)
    session = async_get_clientsession(hass)

    key = entry.data.get("route_key") or entry.entry_id
    runtime = ProxyRuntime(session=session, upstream=entry.data.get(CONF_UPSTREAM, DEFAULT_UPSTREAM))
    view.register_runtime(key, runtime)
    store[entry.entry_id] = {"view": view, "runtime": runtime}

    # repair trip entries once the proxy route exists
    await _repair_trip_entries(hass)

    await hass.config_entries.async_forward_entry_setups(entry, ["sensor"])
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Remove the proxy route."""
    store = hass.data.get(DOMAIN, {})
    data = store.pop(entry.entry_id, None)
    if data is not None:
        view = data["view"]
        key = entry.data.get("route_key") or entry.entry_id
        view.unregister_runtime(key)
    unload_ok = await hass.config_entries.async_unload_platforms(entry, ["sensor"])
    if not store:
        hass.data.pop(DOMAIN, None)
    return unload_ok


async def async_migrate_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Keep migrations trivial."""
    return True
