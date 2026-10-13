"""Diagnostics for the Hase iQ integration."""

from __future__ import annotations

from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST
from homeassistant.core import HomeAssistant

from .const import CONF_OVEN_ID, CONF_REFRESH_TOKEN, GEN1

TO_REDACT = {CONF_HOST, CONF_OVEN_ID, CONF_REFRESH_TOKEN}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: ConfigEntry
) -> dict[str, Any]:
    """Return diagnostics for a config entry."""
    coordinator = entry.runtime_data
    diagnostics: dict[str, Any] = {
        "entry": async_redact_data(dict(entry.data), TO_REDACT),
        "generation": coordinator.generation,
        "last_update_success": coordinator.last_update_success,
        "data": coordinator.data,
    }
    if coordinator.generation != GEN1:
        diagnostics["connected"] = dict(coordinator.client.connected)
    return diagnostics
