"""Binary sensor platform for the Hase iQ integration."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta
import time
from typing import Any

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.event import async_track_time_interval

from .const import GEN1, GEN2_PHASE_ERROR
from .entity import IQStoveAnyCoordinator, IQStoveEntity, app_data, live_data, unix_time

GEN2_ONLINE_TIMEOUT = 180  # seconds without a heartbeat before the stove is offline


@dataclass(frozen=True, kw_only=True)
class IQStoveBinarySensorDescription(BinarySensorEntityDescription):
    """Describes a stove binary sensor."""

    value_fn: Callable[[dict[str, Any]], bool | None]
    node: str | None = None
    # re-evaluate on this interval, for values that depend on the current time
    recheck: timedelta | None = None


def _gen1_error(data: dict[str, Any]) -> bool | None:
    try:
        return bool(int(float(data["appErr"])))
    except (KeyError, TypeError, ValueError):
        return None


def _gen2_online(data: dict[str, Any]) -> bool | None:
    """Return True while the stove's heartbeat `ping` (every 60 s) is recent."""
    ping = unix_time(app_data(data).get("ping"))
    return time.time() - ping < GEN2_ONLINE_TIMEOUT if ping is not None else None


GEN1_BINARY_SENSORS: tuple[IQStoveBinarySensorDescription, ...] = (
    IQStoveBinarySensorDescription(
        key="error",
        translation_key="error",
        device_class=BinarySensorDeviceClass.PROBLEM,
        value_fn=_gen1_error,
    ),
)

GEN2_BINARY_SENSORS: tuple[IQStoveBinarySensorDescription, ...] = (
    IQStoveBinarySensorDescription(
        key="error",
        translation_key="error",
        node="liveData",
        device_class=BinarySensorDeviceClass.PROBLEM,
        value_fn=lambda data: live_data(data).get("F") == GEN2_PHASE_ERROR,
    ),
    IQStoveBinarySensorDescription(
        key="online",
        translation_key="online",
        node="konstant_app",
        device_class=BinarySensorDeviceClass.CONNECTIVITY,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=_gen2_online,
        recheck=timedelta(seconds=30),
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the binary sensors of a stove."""
    coordinator: IQStoveAnyCoordinator = entry.runtime_data
    descriptions = (
        GEN1_BINARY_SENSORS if coordinator.generation == GEN1 else GEN2_BINARY_SENSORS
    )
    async_add_entities(
        IQStoveBinarySensor(coordinator, description) for description in descriptions
    )


class IQStoveBinarySensor(IQStoveEntity, BinarySensorEntity):
    """A stove binary sensor."""

    entity_description: IQStoveBinarySensorDescription

    def __init__(
        self,
        coordinator: IQStoveAnyCoordinator,
        description: IQStoveBinarySensorDescription,
    ) -> None:
        """Initialize the binary sensor."""
        super().__init__(coordinator, description.key, description.node)
        self.entity_description = description

    async def async_added_to_hass(self) -> None:
        """Start the periodic re-check if the description asks for it."""
        await super().async_added_to_hass()
        if (interval := self.entity_description.recheck) is not None:
            self.async_on_remove(
                async_track_time_interval(self.hass, self._async_recheck, interval)
            )

    @callback
    def _async_recheck(self, _now: datetime) -> None:
        self.async_write_ha_state()

    @property
    def is_on(self) -> bool | None:
        """Return True if the stove reports a problem."""
        return self.entity_description.value_fn(self.coordinator.data or {})
