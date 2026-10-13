"""Coordinators for the Hase iQ integration.

`IQStoveCoordinator` drives a Gen 1 stove over its local websocket: the stove
only answers requests, so the coordinator requests values on an interval and
pushes them to Home Assistant as soon as the answers arrive.

`IQStoveCloudCoordinator` mirrors a Gen 2 stove from the HASE cloud. Data is
streamed, so it never polls.
"""

from __future__ import annotations

import asyncio
from datetime import timedelta
import logging
import time
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import CALLBACK_TYPE, HomeAssistant, callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .cloud import HaseCloudError, IQstoveCloud
from .const import CONF_KEEPALIVE_HELD, DOMAIN, GEN1, GEN2, MANUFACTURER
from .IQstove import IQstove

_LOGGER = logging.getLogger(__name__)

GEN1_UPDATE_INTERVAL = timedelta(seconds=5)
GEN1_SETUP_TIMEOUT = 10  # seconds to wait for the first answers
GEN1_STALE_AFTER = 30  # seconds without any frame before the stove counts as gone
PUSH_DELAY = 0.3  # batch frames/events arriving close together into one update

GEN2_READY_TIMEOUT = 10  # seconds to wait for the first snapshot of every node
GEN2_KEEPALIVE_RETRY = 60  # min seconds between keep-alive repairs


class IQStoveCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Gen 1 stove: local websocket."""

    generation = GEN1

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry, stove: IQstove) -> None:
        """Initialize the coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=f"{DOMAIN} ({entry.title})",
            update_interval=GEN1_UPDATE_INTERVAL,
        )
        self.stove = stove
        self._unsub_stove: CALLBACK_TYPE | None = None
        self._push_handle: asyncio.TimerHandle | None = None

    @property
    def serial(self) -> str:
        """Return the stove serial number."""
        return str(self.stove.values.get("_oemser", ""))

    @property
    def device_info(self) -> DeviceInfo:
        """Return the device registry info for this stove."""
        values = self.stove.values
        model_id = values.get("_oemdev")
        return DeviceInfo(
            identifiers={(DOMAIN, self.serial)},
            manufacturer=MANUFACTURER,
            model="Sila Plus" if model_id == "6" else None,
            model_id=model_id,
            name=f"Stove {self.serial}",
            serial_number=self.serial,
            sw_version=f"Wifi {values.get('_wversion')}",
            hw_version=f"Controller {values.get('_oemver')}",
        )

    async def _async_setup(self) -> None:
        """Connect and wait for the info and state values."""
        try:
            await self.stove.connect()
            await self._async_request(
                self.stove.Commands.info + self.stove.Commands.state
            )
        except Exception as err:
            raise UpdateFailed(f"Cannot connect to the stove: {err}") from err

        required = self.stove.Commands.info + self.stove.Commands.state
        deadline = time.monotonic() + GEN1_SETUP_TIMEOUT
        while not all(self.stove.values.get(key) is not None for key in required):
            if time.monotonic() > deadline:
                missing = [k for k in required if self.stove.values.get(k) is None]
                raise UpdateFailed(f"Stove did not answer in time (missing {missing})")
            await asyncio.sleep(0.1)

        self._unsub_stove = self.stove.add_listener(self._on_stove_frame)

    async def _async_update_data(self) -> dict[str, Any]:
        """Request fresh values; the answers are pushed by `_on_stove_frame`."""
        try:
            if not self.stove.connected:
                await self.stove.connect()
            await self._async_request(self.stove.Commands.state)
        except Exception as err:
            raise UpdateFailed(f"Cannot reach the stove: {err}") from err

        last = self.stove.last_message
        if last is None or time.monotonic() - last > GEN1_STALE_AFTER:
            raise UpdateFailed("The stove stopped answering")
        return dict(self.stove.values)

    async def _async_request(self, keys: list[str] | tuple[str, ...]) -> None:
        await asyncio.gather(*(self.stove.getValue(key) for key in keys))

    async def async_set_value(self, key: str, value: int | float | str) -> None:
        """Write a value to the stove and read it back."""
        await self.stove.setValue(key, value)
        await self.stove.getValue(key)

    def _on_stove_frame(self, _update: dict[str, Any]) -> None:
        """Schedule a push to Home Assistant after a frame arrived."""
        if self._push_handle is None:
            self._push_handle = self.hass.loop.call_later(PUSH_DELAY, self._push)

    @callback
    def _push(self) -> None:
        self._push_handle = None
        self.async_set_updated_data(dict(self.stove.values))

    async def async_close(self, release: bool = True) -> None:
        """Stop updates and close the websocket."""
        await self.async_shutdown()
        if self._push_handle is not None:
            self._push_handle.cancel()
            self._push_handle = None
        if self._unsub_stove is not None:
            self._unsub_stove()
            self._unsub_stove = None
        await self.stove.close()


class IQStoveCloudCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Gen 2 stove: HASE cloud (Firebase RTDB), push only.

    `data` maps every streamed node name (see `cloud.NODES`) to its current
    tree. Per-node availability is in `client.connected`.

    The keep-alive counter `k` is incremented once and the fact is stored in
    the config entry. It survives restarts (the stove keeps streaming while
    Home Assistant is down) and is only given back when the entry is unloaded.
    """

    generation = GEN2

    def __init__(
        self, hass: HomeAssistant, entry: ConfigEntry, client: IQstoveCloud
    ) -> None:
        """Initialize the coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=f"{DOMAIN} ({entry.title})",
            update_interval=None,
        )
        self.client = client
        self._unsub_client: CALLBACK_TYPE | None = None
        self._push_handle: asyncio.TimerHandle | None = None
        self._keepalive_repaired = 0.0
        self._keepalive_task: asyncio.Task | None = None

    @property
    def serial(self) -> str:
        """Return the stove serial number."""
        return self.client.serial

    @property
    def device_info(self) -> DeviceInfo:
        """Return the device registry info for this stove."""
        konstant = self.client.data.get("konstant")
        model = konstant.get("verz") if isinstance(konstant, dict) else None
        return DeviceInfo(
            identifiers={(DOMAIN, self.serial)},
            manufacturer=MANUFACTURER,
            model=str(model) if model else None,
            name=f"Stove {self.serial}",
            serial_number=self.serial,
        )

    @property
    def keepalive_held(self) -> bool:
        """Return True if this entry currently holds a keep-alive count."""
        return bool(self.config_entry.data.get(CONF_KEEPALIVE_HELD))

    async def _async_setup(self) -> None:
        """Check the oven exists, take the keep-alive and start streaming."""
        try:
            konstant = await self.client.async_get(f"konstant/{self.client.oven_id}")
            if konstant is None:
                raise UpdateFailed("The stove is not known to the HASE cloud")
            if not self.keepalive_held:
                await self.client.async_add_keepalive(1)
                self._set_keepalive_held(True)
        except HaseCloudError as err:
            raise UpdateFailed(f"Cannot reach the HASE cloud: {err}") from err

        self._unsub_client = self.client.add_listener(self._on_client_change)
        self.client.start()
        if not await self.client.async_wait_ready(GEN2_READY_TIMEOUT):
            missing = [n for n, up in self.client.connected.items() if not up]
            _LOGGER.debug("Nodes without first snapshot after setup: %s", missing)
        if not any(self.client.connected.values()):
            raise UpdateFailed("Cannot stream from the HASE cloud")

    async def _async_update_data(self) -> dict[str, Any]:
        """Return the current snapshot (data itself is pushed)."""
        return dict(self.client.data)

    def _on_client_change(self, node: str) -> None:
        if node == "konstant":
            self._check_keepalive()
        if self._push_handle is None:
            self._push_handle = self.hass.loop.call_later(PUSH_DELAY, self._push)

    @callback
    def _push(self) -> None:
        self._push_handle = None
        self.async_set_updated_data(dict(self.client.data))

    def _check_keepalive(self) -> None:
        """Re-take the keep-alive if `k` dropped below 1 while we hold it."""
        konstant = self.client.data.get("konstant")
        k = konstant.get("k") if isinstance(konstant, dict) else None
        if (
            not isinstance(k, (int, float))
            or k >= 1
            or not self.keepalive_held
            or time.monotonic() - self._keepalive_repaired < GEN2_KEEPALIVE_RETRY
            or (self._keepalive_task is not None and not self._keepalive_task.done())
        ):
            return
        self._keepalive_repaired = time.monotonic()
        _LOGGER.info("Keep-alive counter dropped to %s, taking it again", k)
        self._keepalive_task = self.config_entry.async_create_background_task(
            self.hass, self._async_repair_keepalive(), "haseiq keep-alive repair"
        )

    async def _async_repair_keepalive(self) -> None:
        try:
            await self.client.async_add_keepalive(1)
        except HaseCloudError as err:
            _LOGGER.warning("Could not restore the keep-alive counter: %s", err)

    def _set_keepalive_held(self, held: bool) -> None:
        self.hass.config_entries.async_update_entry(
            self.config_entry,
            data={**self.config_entry.data, CONF_KEEPALIVE_HELD: held},
        )

    async def async_close(self, release: bool = True) -> None:
        """Stop streaming; with `release`, give the keep-alive count back."""
        await self.async_shutdown()
        if self._push_handle is not None:
            self._push_handle.cancel()
            self._push_handle = None
        if self._unsub_client is not None:
            self._unsub_client()
            self._unsub_client = None
        await self.client.async_close()
        if release and self.keepalive_held:
            try:
                await self.client.async_add_keepalive(-1)
            except HaseCloudError as err:
                _LOGGER.warning("Could not release the keep-alive counter: %s", err)
            self._set_keepalive_held(False)
