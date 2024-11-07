"""The Hase iQ integration."""

from __future__ import annotations

import asyncio
from datetime import timedelta
import logging

from homeassistant import config_entries
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .const import DOMAIN
from .coordinator import IQStoveCoordinator
from .IQstove import IQstove

_LOGGER = logging.getLogger(__name__)
PLATFORMS: list[Platform] = [Platform.SENSOR]


async def async_setup_entry(hass: HomeAssistant, entry: config_entries.ConfigEntry):
    """Set up IQ Stove from a config entry."""
    # print("__init__ async setup entry")
    # print(entry.data)
    stove = IQstove(entry.data["host"], 8080)
    coordinator = IQStoveCoordinator(hass, entry, stove, 5)
    await coordinator.async_config_entry_first_refresh()
    # print("__init__ async setup entry after await coordinator refresh")
    # Store the coordinator in the hass data
    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


#

# from __future__ import annotations

# from datetime import timedelta
# import logging

# from homeassistant.config_entries import ConfigEntry
# from homeassistant.const import Platform
# from homeassistant.core import HomeAssistant
# from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

# from .const import DOMAIN
# from .IQstove import IQstove

# _LOGGER = logging.getLogger(__name__)

# # TODO List the platforms that you want to support.
# # For your initial PR, limit it to 1 platform.
# PLATFORMS: list[Platform] = [Platform.BINARY_SENSOR]

# # TODO Create ConfigEntry type alias with API object
# # Alias name should be prefixed by integration name
# # type New_NameConfigEntry = ConfigEntry[MyApi]  # noqa: F821


# class IQStoveCoordinator(DataUpdateCoordinator):
#     def __init__(self, hass, iq_stove):
#         """Initialize the data update coordinator."""
#         self.iq_stove = iq_stove

#         # Define the update interval
#         update_interval = timedelta(seconds=30)  # fetch data every 30 seconds

#         # Initialize the DataUpdateCoordinator with Home Assistant
#         super().__init__(
#             hass,
#             _LOGGER,
#             name="IQStove",
#             update_interval=update_interval,
#         )

#     async def _async_setup(self):
#         """Set up the coordinator and fetch initial device data."""
#         try:
#             # Fetch device details, e.g., model, serial, etc.
#             print(f"Async setup {await self.iq_stove.getValue("_oemdev")}")
#             self._device_info["model"] = 123
#             # self._device_info["serial"] = await self.iq_stove.get_value("_oemser")
#             # _LOGGER.info(
#             #     f"Connected to IQStove model: {self._device_info['model']}, Serial: {self._device_info['serial']}"
#             # )

#         except Exception as error:
#             raise UpdateFailed(f"Failed to set up device info: {error}")

#     async def _async_update_data(self):
#         """Fetch data from IQStove."""
#         try:
#             # Example: fetch multiple values
#             return {
#                 # "temperature": await self.iq_stove.get_value("appT"),
#                 # "performance": await self.iq_stove.get_value("appP"),
#                 # "phase": await self.iq_stove.get_value("appPhase"),
#             }
#         except Exception as error:
#             raise UpdateFailed(f"Failed to fetch data: {error}")


# # TODO Update entry annotation
# async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
#     """Set up Hase iQ from a config entry."""

#     # Initialize IQStove device
#     iq_stove = IQstove("192.168.1.158", 8080)
#     await iq_stove.connectAndUpdate()  # Call the async initialize method

#     # # Create the coordinator
#     coordinator = IQStoveCoordinator(hass, iq_stove)

#     # # Fetch initial data
#     await coordinator.async_config_entry_first_refresh()

#     """Set up platform from a ConfigEntry."""
#     hass.data.setdefault(DOMAIN, {})
#     hass.data[DOMAIN][entry.entry_id] = entry.data
#     await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

#     return True


# # TODO Update entry annotation
# async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
#     """Unload a config entry."""
#     return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
