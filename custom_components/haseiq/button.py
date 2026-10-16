"""Button platform for the Hase iQ integration (Gen 2 only)."""

from __future__ import annotations

from datetime import datetime

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import CALLBACK_TYPE, HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.event import async_call_later

from .const import GEN2
from .coordinator import IQStoveCloudCoordinator
from .entity import IQStoveEntity

# The stove clears the booster itself after ~70 s; this is only a safety ceiling
# so a write can never leave it stuck on.
BOOSTER_RESET = 300  # seconds


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
    """Triggers the stove's "extra air" booster (a short burst of more air)."""

    _attr_translation_key = "extra_air"

    coordinator: IQStoveCloudCoordinator

    def __init__(self, coordinator: IQStoveCloudCoordinator) -> None:
        """Initialize the entity."""
        super().__init__(coordinator, "extra_air", "konstant_app")
        self._cancel_reset: CALLBACK_TYPE | None = None

    async def async_press(self) -> None:
        """Start the booster and arm the safety reset."""
        await self.coordinator.async_set_booster(True)
        self._cancel_pending_reset()
        self._cancel_reset = async_call_later(self.hass, BOOSTER_RESET, self._async_reset)

    async def _async_reset(self, _now: datetime) -> None:
        self._cancel_reset = None
        await self.coordinator.async_set_booster(False)

    def _cancel_pending_reset(self) -> None:
        if self._cancel_reset is not None:
            self._cancel_reset()
            self._cancel_reset = None

    async def async_will_remove_from_hass(self) -> None:
        """Cancel the safety reset when the entity goes away."""
        self._cancel_pending_reset()
