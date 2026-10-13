"""Binary sensor platform for the Hase iQ integration."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import GEN1, GEN2_PHASE_ERROR
from .entity import IQStoveAnyCoordinator, IQStoveEntity, live_data


@dataclass(frozen=True, kw_only=True)
class IQStoveBinarySensorDescription(BinarySensorEntityDescription):
    """Describes a stove binary sensor."""

    value_fn: Callable[[dict[str, Any]], bool | None]
    node: str | None = None


def _gen1_error(data: dict[str, Any]) -> bool | None:
    try:
        return bool(int(float(data["appErr"])))
    except (KeyError, TypeError, ValueError):
        return None


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
        value_fn=lambda data: live_data(data).get("P") == GEN2_PHASE_ERROR,
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

    @property
    def is_on(self) -> bool | None:
        """Return True if the stove reports a problem."""
        return self.entity_description.value_fn(self.coordinator.data or {})
