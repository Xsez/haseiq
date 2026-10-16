"""Diagnostics for the Hase iQ integration."""

from __future__ import annotations

from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST
from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util

from .cloud import HaseCloudError
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
        diagnostics["error_log"] = await _async_error_log(coordinator.client)
    return diagnostics


async def _async_error_log(client: Any) -> Any:
    """Return the Gen 2 error log as `["<local time> <code>", ...]`, oldest first.

    It is only read here, on download, since it can be several MB.
    """
    try:
        log = await client.async_get_error_log()
    except HaseCloudError as err:
        return f"Cannot read the error log: {err}"
    if not isinstance(log, dict):
        return []
    lines = []
    for key in sorted((key for key in log if key.isdigit()), key=int):
        entry = log[key]
        code = entry.get("ecode2", entry) if isinstance(entry, dict) else entry
        if key == "0":  # not a time; the code the log started with
            lines.append(f"start {code}")
            continue
        time = dt_util.as_local(dt_util.utc_from_timestamp(int(key)))
        lines.append(f"{time:%Y-%m-%d %H:%M:%S} {code}")
    return lines
