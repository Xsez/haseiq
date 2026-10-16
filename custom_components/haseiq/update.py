"""Update platform for the Hase iQ integration (Gen 2 only)."""

from __future__ import annotations

from typing import Any

from homeassistant.components.update import (
    UpdateDeviceClass,
    UpdateEntity,
    UpdateEntityFeature,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import GEN2
from .coordinator import IQStoveCloudCoordinator
from .entity import IQStoveEntity, app_data

# The cloud only signals that an update exists, not the target version.
UPDATE_AVAILABLE = "available"


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the firmware update entity of a stove."""
    coordinator = entry.runtime_data
    if coordinator.generation == GEN2:
        async_add_entities([IQStoveFirmwareUpdate(coordinator)])


class IQStoveFirmwareUpdate(IQStoveEntity, UpdateEntity):
    """Firmware update for a Gen 2 stove (`konstant_app/v`, install via `konstant/u`)."""

    _attr_device_class = UpdateDeviceClass.FIRMWARE
    _attr_supported_features = (
        UpdateEntityFeature.INSTALL | UpdateEntityFeature.PROGRESS
    )
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_translation_key = "firmware"

    coordinator: IQStoveCloudCoordinator

    def __init__(self, coordinator: IQStoveCloudCoordinator) -> None:
        """Initialize the entity."""
        super().__init__(coordinator, "firmware", "konstant_app")
        self._installing = False
        self._install_base: str | None = None

    @property
    def installed_version(self) -> str | None:
        """Return the current firmware version (e.g. 19.08.26e)."""
        app = app_data(self.coordinator.data)
        version = app.get("vers")
        return f"{version}{app.get('versu') or ''}" if version else None

    @property
    def latest_version(self) -> str | None:
        """Return a newer version marker while an update is offered (`v`)."""
        if app_data(self.coordinator.data).get("v") is True:
            return UPDATE_AVAILABLE
        return self.installed_version

    @property
    def in_progress(self) -> bool:
        """Return True while we are installing."""
        return self._installing

    @property
    def update_percentage(self) -> float | None:
        """Return the download progress (`f`) while installing."""
        if not self._installing:
            return None
        value = app_data(self.coordinator.data).get("f")
        return float(value) if isinstance(value, (int, float)) and not isinstance(value, bool) else None

    async def async_install(self, version: str | None, backup: bool, **kwargs: Any) -> None:
        """Start the firmware update on the stove."""
        self._install_base = self.installed_version
        self._installing = True
        self.async_write_ha_state()
        try:
            await self.coordinator.async_start_update()
        except Exception:
            self._installing = False
            self.async_write_ha_state()
            raise

    @callback
    def _handle_coordinator_update(self) -> None:
        # stop showing progress once the update cleared or the version changed
        if self._installing and (
            app_data(self.coordinator.data).get("v") is not True
            or self.installed_version != self._install_base
        ):
            self._installing = False
        super()._handle_coordinator_update()
