"""Manage data fetching and updates for the IQ Stove integration.

The IQStoveCoordinator class handles communication and state updates for the IQ Stove in Home Assistant.
"""

import asyncio
from datetime import timedelta
import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .const import DOMAIN
from .IQstove import IQstove, IQStoveConnectionError

_LOGGER = logging.getLogger(__name__)


class IQStoveCoordinator(DataUpdateCoordinator):
    """Class to manage the fetching of data from the IQ Stove."""

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        stove: IQstove,
        update_interval: int = 30,
    ) -> None:
        """Initialize the coordinator."""
        # store stove object in self
        self.stove = stove

        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN} ({entry.unique_id})",
            update_interval=timedelta(seconds=update_interval),
        )

    async def _async_setup(self):
        """Fetch data for the first time before any platform entities are created."""
        try:
            _LOGGER.debug("Starting stove setup...")
            # if stove not connected, await reconnect and restart listener task
            if not self.stove.connected:
                await self.stove.connect()
                _LOGGER.debug("Stove connected successfully")

            # Fetch all data which we only need once
            for cmd in self.stove.Commands.info:
                self.stove.getValue(cmd)
                _LOGGER.debug("Started fetching info command: %s", cmd)

            # Fetch all state data from stove
            for cmd in self.stove.Commands.state:
                self.stove.getValue(cmd)
                _LOGGER.debug("Started fetching state command: %s", cmd)

            # Wait until values are populated or timeout occurs
            timeout = 10  # Maximum wait time in seconds
            interval = 0.1  # Check interval in seconds
            elapsed_time = 0

            while (
                not self._are_values_populated(
                    self.stove.Commands.info + self.stove.Commands.state
                )
                and elapsed_time < timeout
            ):
                await asyncio.sleep(interval)
                elapsed_time += interval
                _LOGGER.debug(
                    "Waiting for values to populate... (%s seconds elapsed)",
                    elapsed_time,
                )

            if not self._are_values_populated(
                self.stove.Commands.info + self.stove.Commands.state
            ):
                _LOGGER.error("Values failed to populate within the timeout period")
                raise TimeoutError("IQStove values did not populate in time")

            _LOGGER.debug("Stove setup completed successfully")

        except Exception as e:
            _LOGGER.error("Error during setup: %s", e)
            raise

    def _are_values_populated(self, commands):
        """Check if the required commands have been populated in the stove's values."""
        return all(
            cmd in self.stove.values and self.stove.values[cmd] is not None
            for cmd in commands
        )

    async def _async_update_data(self):
        """Fetch data from the IQ Stove. Return data to callback '_handle_coordinator_update' in platform."""
        try:
            _LOGGER.debug("Starting data update")
            # if stove not connected, await reconnect and restart listener task
            if not self.stove.connected:
                await self.stove.connect()
                _LOGGER.debug("Stove reconnected successfully")
            # get all state data from stove
            for cmd in self.stove.Commands.state:
                await self.stove.getValue(cmd)
                _LOGGER.debug("Started fetching state command: %s", cmd)
            # give a little bit of time for the stove to respond and update values
            # await asyncio.sleep(0.1)
            _LOGGER.debug("Data update completed successfully")
        except IQStoveConnectionError as e:
            _LOGGER.error("Connection error from IQStove: %s", e)
        except Exception as e:
            _LOGGER.error("Unexpected error during data update: %s", e)
        return self.stove.values
