import asyncio
from datetime import timedelta
import logging
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import DOMAIN, HomeAssistant
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
        # print("Coordinator Init")
        """Initialize the coordinator."""
        self.stove = stove
        # self.update_interval = timedelta(seconds=update_interval)

        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN} ({config_entry.unique_id})",
            update_method=self.async_update_data,
            update_interval=timedelta(seconds=update_interval),
        )

    async def _async_setup(self):
        """Set up the coordinator

        This is the place to set up your coordinator,
        or to load data, that only needs to be loaded once.

        This method will be called automatically during
        coordinator.async_config_entry_first_refresh.
        """
        # print("Coordinator Async Setup")
        if not self.stove.connected:
            await self.stove.connect()
        for cmd in self.stove.Commands.info:
            self.stove.getValue(cmd)
        await asyncio.sleep(0.5)
        # print(self.stove.values)
        # print("Coordinator Async Setup finished")

    async def async_update_data(self):
        """Fetch data from the IQ Stove."""
        # await self.stove.sendPeriodicRequest()  # You can adjust this based on your needs
        if not self.stove.connected:
            await self.stove.connect()
        for cmd in self.stove.Commands.state:
            self.stove.getValue(cmd)
        await asyncio.sleep(0.5)
        # print("Coordinator Async Update Data", self.stove.values)
        return self.stove.values
