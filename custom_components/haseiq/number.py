"""Number platform for the Hase iQ integration (Gen 1 only)."""

from __future__ import annotations

from homeassistant.components.number import NumberEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import PERCENTAGE
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import GEN1
from .coordinator import IQStoveCoordinator
from .entity import IQStoveEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the number entities of a stove."""
    coordinator = entry.runtime_data
    if coordinator.generation == GEN1:
        async_add_entities([IQStoveLedBrightness(coordinator)])


class IQStoveLedBrightness(IQStoveEntity, NumberEntity):
    """LED brightness of a Gen 1 stove."""

    _attr_translation_key = "led_brightness"
    _attr_native_min_value = 0
    _attr_native_max_value = 100
    _attr_native_step = 1
    _attr_native_unit_of_measurement = PERCENTAGE

    coordinator: IQStoveCoordinator

    def __init__(self, coordinator: IQStoveCoordinator) -> None:
        """Initialize the entity."""
        super().__init__(coordinator, "led_brightness")

    @property
    def native_value(self) -> float | None:
        """Return the current brightness."""
        value = (self.coordinator.data or {}).get("_ledBri")
        return float(value) if value is not None else None

    async def async_set_native_value(self, value: float) -> None:
        """Set the brightness."""
        await self.coordinator.async_set_value("_ledBri", int(value))
