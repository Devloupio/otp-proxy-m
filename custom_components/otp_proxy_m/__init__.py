"""The OTP Proxy M integration.

Sets up an unauthenticated HTTP view that proxies requests to the
mobilites-m OTP2 server, rewriting WAF-blocked GraphQL payloads.
"""

from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import CONF_UPSTREAM, DEFAULT_UPSTREAM, DOMAIN
from .http import ProxyRuntime, get_or_create_view

_LOGGER = logging.getLogger(__name__)

PLATFORMS = ["sensor"]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Register the proxy route for this entry."""
    store = hass.data.setdefault(DOMAIN, {})
    view = get_or_create_view(hass)
    session = hass.helpers.aiohttp_client.async_get_clientsession()

    key = entry.data.get("route_key") or entry.entry_id
    runtime = ProxyRuntime(session=session, upstream=entry.data.get(CONF_UPSTREAM, DEFAULT_UPSTREAM))
    view.register_runtime(key, runtime)
    store[entry.entry_id] = {"view": view, "runtime": runtime}

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
