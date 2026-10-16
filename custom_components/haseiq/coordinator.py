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
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .cloud import HaseCloudError, IQstoveCloud, firing_stats
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
    tree. Per-node availability is in `client.connected`. `data["firing"]`
    holds statistics of the newest firing (see `cloud.firing_stats`) and the
    number of firings the cloud keeps; it is reloaded whenever the firing
    list changes, which happens every minute while the stove burns.

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
        self._firing: dict[str, Any] | None = None
        self._firing_start: str | None = None
        self._firing_count: int | None = None
        self._firing_task: asyncio.Task | None = None
        self._sw_version: str | None = None
        self._air_flap_threshold: int | None = None
        self._model: dict[str, Any] | None = None
        # pulses of `konstant_app/n` seen so far (see `_check_notification`)
        self.notification_count = 0
        self._notification_pending = False

    @property
    def serial(self) -> str:
        """Return the stove serial number."""
        return self.client.serial

    @property
    def device_info(self) -> DeviceInfo:
        """Return the device registry info for this stove."""
        app = self.client.data.get("konstant_app")
        model_id = app.get("ofen") if isinstance(app, dict) else None
        # prefer the real model name from stove_models; fall back to the verz tag
        konstant = self.client.data.get("konstant")
        model = (self._model or {}).get("name") or (
            konstant.get("verz") if isinstance(konstant, dict) else None
        )
        docs_url = (self._model or {}).get("technical_data_url")
        return DeviceInfo(
            identifiers={(DOMAIN, self.serial)},
            manufacturer=MANUFACTURER,
            model=str(model) if model else None,
            model_id=str(model_id) if model_id is not None else None,
            name=f"Stove {self.serial}",
            serial_number=self.serial,
            sw_version=self._firmware(),
            configuration_url=docs_url or None,
        )

    def _firmware(self) -> str | None:
        """Return the firmware version and build time of the stove.

        The version is `vers` plus the letter `versu` ("19.08.26" + "e", as the
        stove's own log calls it), the build time is `cz`.
        """
        app = self.client.data.get("konstant_app")
        if not isinstance(app, dict) or not app.get("vers"):
            return None
        version = f"{app['vers']}{app.get('versu') or ''}"
        return f"{version} ({app['cz']})" if app.get("cz") else version

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

        await self._async_load_model()

    async def _async_load_model(self) -> None:
        """Look up the stove model once (name, air-flap threshold K, image, docs)."""
        app = self.client.data.get("konstant_app")
        article = app.get("a") if isinstance(app, dict) else None
        if article is None:
            return
        try:
            model = await self.client.async_get_stove_model(str(article))
        except HaseCloudError as err:
            _LOGGER.debug("Cannot load the stove model: %s", err)
            return
        if not model:
            return
        self._model = model
        threshold = model.get("air_flap_threshold")
        if isinstance(threshold, int) and 0 < threshold < 100:
            self._air_flap_threshold = threshold
        _LOGGER.debug("Stove model %s, K=%s (article %s)", model.get("name"), threshold, article)

    @property
    def model(self) -> dict[str, Any] | None:
        """Return the stove_models entry (name, img_url, …), if loaded."""
        return self._model

    async def _async_update_data(self) -> dict[str, Any]:
        """Return the current snapshot (data itself is pushed)."""
        return self._snapshot()

    async def async_set_value(self, key: str, value: int | float | str) -> None:
        """Write a setting to `konstant`; the stream brings the new value back."""
        try:
            await self.client.async_set_konstant(key, value)
        except HaseCloudError as err:
            raise HomeAssistantError(f"Cannot write to the HASE cloud: {err}") from err

    async def async_start_update(self) -> None:
        """Start the firmware update (writes `konstant/u` = true, like the app)."""
        try:
            await self.client.async_set_konstant("u", True)
        except HaseCloudError as err:
            raise HomeAssistantError(f"Cannot write to the HASE cloud: {err}") from err

    async def async_pulse_booster(self) -> None:
        """Request extra air: pulse `konstant/b` true for ~2 s, then false.

        `b` is the momentary command the app sends; the stove confirms by setting
        `konstant_app/ba` (booster active) and returns to iQ mode on its own.
        """
        try:
            await self.client.async_set_konstant("b", True)
        except HaseCloudError as err:
            raise HomeAssistantError(f"Cannot write to the HASE cloud: {err}") from err
        try:
            await asyncio.sleep(2)
        finally:
            try:
                await self.client.async_set_konstant("b", False)
            except HaseCloudError as err:
                _LOGGER.warning("Could not reset the booster pulse `b`: %s", err)

    def _snapshot(self) -> dict[str, Any]:
        return {
            **self.client.data,
            "firing": self._firing,
            "air_flap_threshold": self._air_flap_threshold,
        }

    def _on_client_change(self, node: str) -> None:
        if node == "konstant":
            self._check_keepalive()
        elif node == "konstant_app":
            self._check_notification()
        elif node == "historienliste":
            self._load_firing()
        self._schedule_push()

    def _check_notification(self) -> None:
        """Count app notifications.

        The stove sets `n` to request a push notification to the app, and the
        cloud resets it within about a second. That is shorter than the push
        delay, so pulses are counted here, on every change, not in the pushed
        snapshot.
        """
        app = self.client.data.get("konstant_app")
        pending = bool(app.get("n")) if isinstance(app, dict) else False
        if pending and not self._notification_pending:
            self.notification_count += 1
        self._notification_pending = pending

    def _schedule_push(self) -> None:
        if self._push_handle is None:
            self._push_handle = self.hass.loop.call_later(PUSH_DELAY, self._push)

    @callback
    def _push(self) -> None:
        self._push_handle = None
        self._update_firmware()
        self.async_set_updated_data(self._snapshot())

    def _update_firmware(self) -> None:
        """Keep the device's firmware current; the stove updates over the air."""
        firmware = self._firmware()
        if firmware == self._sw_version:
            return
        self._sw_version = firmware
        registry = dr.async_get(self.hass)
        if device := registry.async_get_device(identifiers={(DOMAIN, self.serial)}):
            registry.async_update_device(device.id, sw_version=firmware)

    def _load_firing(self) -> None:
        """Reload the statistics of the newest firing in the background.

        A change that arrives while a load runs is skipped; the next one comes
        a minute later.
        """
        if self._firing_task is not None and not self._firing_task.done():
            return
        self._firing_task = self.config_entry.async_create_background_task(
            self.hass, self._async_load_firing(), "haseiq firing statistics"
        )

    async def _async_load_firing(self) -> None:
        history = self.client.data.get("historienliste")
        starts = [key for key in history if key.isdigit()] if isinstance(history, dict) else []
        if not starts:
            return
        newest = max(starts, key=int)
        try:
            if newest != self._firing_start or self._firing_count is None:
                self._firing_count = len(await self.client.async_get_firing_starts())
            samples = await self.client.async_get_firing(newest)
        except HaseCloudError as err:
            _LOGGER.debug("Cannot load the firing history: %s", err)
            return
        self._firing_start = newest
        self._firing = {"count": self._firing_count, **(firing_stats(samples) or {})}
        self._schedule_push()

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
