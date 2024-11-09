"""The Hase iQ integration."""

from __future__ import annotations

import logging

from homeassistant import config_entries
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant

from .const import DOMAIN
from .coordinator import IQStoveCoordinator
from .IQstove import IQstove

_LOGGER = logging.getLogger(__name__)
PLATFORMS: list[Platform] = [Platform.BINARY_SENSOR, Platform.SENSOR]

async def async_setup_entry(hass: HomeAssistant, entry: config_entries.ConfigEntry):
    """Set up IQ Stove from a config entry."""
    # Create stove object with host from config entry
    stove = IQstove(entry.data["host"], 8080)
    # create coordinator and pass stove object
    coordinator = IQStoveCoordinator(hass, entry, stove, 5)
    await coordinator.async_config_entry_first_refresh()
    # Store the coordinator in the entry runtime_data
    entry.runtime_data = coordinator
    # Setup the prlatforms provided by the list PLATFORMS
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    # finish
    return True
