import asyncio
from datetime import timedelta
import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .const import DOMAIN
from .IQstove import IQstove

_LOGGER = logging.getLogger(__name__)


class IQStoveCoordinator(DataUpdateCoordinator):
    """Class to manage the fetching of data from the IQ Stove."""

    def __init__(
        self,
        hass: HomeAssistant,
        config_entry: ConfigEntry,
        stove: IQstove,
        update_interval: int = 30,
    ):
        """Initialize the coordinator."""
        # store stove object in self
        self.stove = stove

        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN} ({config_entry.unique_id})",
            update_method=self.async_update_data,
            update_interval=timedelta(seconds=update_interval),
        )

    async def _async_setup(self):
        """Fetch data for the first time before any platform entities are created."""
        # if stove not connected, await reconnect and restart listener task
        if not self.stove.connected:
            await self.stove.connect()
        # get all data which we only need once
        for cmd in self.stove.Commands.info:
            self.stove.getValue(cmd)
        # get all state data from stove
        for cmd in self.stove.Commands.state:
            self.stove.getValue(cmd)
        # give a litle bit of time for the stove to respond and updated values
        await asyncio.sleep(0.5)

    async def async_update_data(self):
        """Fetch data from the IQ Stove. Return data to callback '_handle_coordinator_update' in platform"""
        # if stove not connected, await reconnect and restart listener task
        if not self.stove.connected:
            await self.stove.connect()
        # get all state data from stove
        for cmd in self.stove.Commands.state:
            self.stove.getValue(cmd)
        # give a litle bit of time for the stove to respond and updated values
        await asyncio.sleep(0.1)
        return self.stove.values
