"""Event platform for the Hase iQ integration (Gen 2 only)."""

from __future__ import annotations

from homeassistant.components.event import EventEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import GEN2
from .coordinator import IQStoveCloudCoordinator
from .entity import IQStoveEntity

EVENT_NOTIFICATION = "notification"


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the event entities of a stove."""
    coordinator = entry.runtime_data
    if coordinator.generation == GEN2:
        async_add_entities([IQStoveNotificationEvent(coordinator)])


class IQStoveNotificationEvent(IQStoveEntity, EventEntity):
    """Fires when the stove asks the cloud to notify the HASE iQ app.

    So far this happened exactly when the phase changed to add wood. The
    phase arrives a few seconds after the notification, so it is not part of
    the event.
    """

    _attr_translation_key = "app_notification"
    _attr_event_types = [EVENT_NOTIFICATION]

    coordinator: IQStoveCloudCoordinator

    def __init__(self, coordinator: IQStoveCloudCoordinator) -> None:
        """Initialize the entity."""
        super().__init__(coordinator, "app_notification", "konstant_app")
        self._seen = coordinator.notification_count

    @callback
    def _handle_coordinator_update(self) -> None:
        """Fire once per new notification, then write the state."""
        if self.coordinator.notification_count > self._seen:
            self._seen = self.coordinator.notification_count
            self._trigger_event(EVENT_NOTIFICATION)
        super()._handle_coordinator_update()
