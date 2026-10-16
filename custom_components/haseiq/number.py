"""Number platform for the Hase iQ integration."""

from __future__ import annotations

from dataclasses import dataclass

from homeassistant.components.number import NumberEntity, NumberEntityDescription
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import PERCENTAGE
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import GEN1
from .entity import IQStoveAnyCoordinator, IQStoveEntity


@dataclass(frozen=True, kw_only=True)
class IQStoveNumberDescription(NumberEntityDescription):
    """Describes a stove setting.

    `value_key` is the key the stove reports and is written to; for Gen 2 it
    lives in `node`.
    """

    value_key: str
    node: str | None = None
    native_min_value: float = 0
    native_max_value: float = 100
    native_step: float = 1
    native_unit_of_measurement: str | None = PERCENTAGE


GEN1_NUMBERS: tuple[IQStoveNumberDescription, ...] = (
    IQStoveNumberDescription(
        key="led_brightness",
        translation_key="led_brightness",
        value_key="_ledBri",
    ),
)

GEN2_NUMBERS: tuple[IQStoveNumberDescription, ...] = (
    IQStoveNumberDescription(
        key="signal_led_brightness",
        translation_key="signal_led_brightness",
        value_key="l",
        node="konstant",
    ),
    IQStoveNumberDescription(
        key="switch_led_brightness",
        translation_key="switch_led_brightness",
        value_key="s",
        node="konstant",
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the number entities of a stove."""
    coordinator: IQStoveAnyCoordinator = entry.runtime_data
    descriptions = GEN1_NUMBERS if coordinator.generation == GEN1 else GEN2_NUMBERS
    async_add_entities(
        IQStoveNumber(coordinator, description) for description in descriptions
    )


class IQStoveNumber(IQStoveEntity, NumberEntity):
    """A stove setting."""

    entity_description: IQStoveNumberDescription

    def __init__(
        self, coordinator: IQStoveAnyCoordinator, description: IQStoveNumberDescription
    ) -> None:
        """Initialize the entity."""
        super().__init__(coordinator, description.key, description.node)
        self.entity_description = description

    @property
    def native_value(self) -> float | None:
        """Return the current value."""
        data = self.coordinator.data or {}
        if self.entity_description.node is not None:
            data = data.get(self.entity_description.node)
            if not isinstance(data, dict):
                return None
        try:
            return float(data[self.entity_description.value_key])
        except (KeyError, TypeError, ValueError):
            return None

    async def async_set_native_value(self, value: float) -> None:
        """Write the value to the stove."""
        await self.coordinator.async_set_value(
            self.entity_description.value_key, int(value)
        )
