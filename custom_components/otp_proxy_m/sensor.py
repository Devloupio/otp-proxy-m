"""Sensor exposing proxy health and counters."""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN, STATE_DOWN, STATE_ERROR, STATE_OK
from .http import ProxyRuntime

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up the status sensor."""
    store = hass.data[DOMAIN][entry.entry_id]
    runtime: ProxyRuntime = store["runtime"]
    key = entry.data.get("route_key") or entry.entry_id
    async_add_entities([OtpProxyStatusSensor(hass, entry, runtime, key)])


class OtpProxyStatusSensor(SensorEntity):
    """Reports proxy health and counters."""

    _attr_state_class = None
    _attr_has_entity_name = True

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry, runtime: ProxyRuntime, key: str) -> None:
        self._runtime = runtime
        self._key = key
        self._attr_unique_id = f"{entry.entry_id}-status"
        self._attr_name = "Status"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=f"OTP Proxy M ({key})",
            manufacturer="devloupio",
            model="WAF-safe OTP2 proxy",
            entry_type=DeviceEntryType.SERVICE,
        )

    @property
    def native_value(self) -> str:
        stats = self._runtime.stats
        if stats.errors_total and (stats.last_success_at is None or stats.last_success_at < (stats.last_request_at or 0) - 300):
            return STATE_DOWN
        if stats.errors_total and stats.last_error:
            return STATE_ERROR
        return STATE_OK

    @property
    def extra_state_attributes(self) -> dict:
        stats = self._runtime.stats
        return {
            "route_url": f"/otp_proxy_m/{self._key}/otp/routers/default",
            "upstream": self._runtime.upstream_base,
            "requests_total": stats.requests_total,
            "rewrites_total": stats.rewrites_total,
            "errors_total": stats.errors_total,
            "upstream_403_total": stats.upstream_403_total,
            "last_error": stats.last_error,
            "last_request_at": self._iso(stats.last_request_at),
            "last_success_at": self._iso(stats.last_success_at),
        }

    @staticmethod
    def _iso(ts: float | None) -> str | None:
        if ts is None:
            return None
        return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()

    @property
    def icon(self) -> str:
        return "mdi:bus-multiple"
