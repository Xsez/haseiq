"""Button platform for the Hase iQ integration (Gen 2 only)."""

from __future__ import annotations

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import GEN2
from .coordinator import IQStoveCloudCoordinator
from .entity import IQStoveEntity, app_data


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the buttons of a stove."""
    coordinator = entry.runtime_data
    if coordinator.generation == GEN2:
        async_add_entities([IQStoveBoosterButton(coordinator)])


class IQStoveBoosterButton(IQStoveEntity, ButtonEntity):
    """Requests the stove's "extra air" booster (a short burst of more air)."""

    _attr_translation_key = "extra_air"

    coordinator: IQStoveCloudCoordinator

    def __init__(self, coordinator: IQStoveCloudCoordinator) -> None:
        """Initialize the entity."""
        super().__init__(coordinator, "extra_air", "konstant_app")

    @property
    def available(self) -> bool:
        """Available only while the stove offers the booster and it is not running."""
        if not super().available:
            return False
        app = app_data(self.coordinator.data)
        return app.get("bv") is True and app.get("ba") is not True

    async def async_press(self) -> None:
        """Pulse the booster command; the stove runs it and ends it on its own."""
        await self.coordinator.async_pulse_booster()
