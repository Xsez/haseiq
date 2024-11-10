"""Platform for sensor integration."""

from __future__ import annotations

from homeassistant.components.number import (
    NumberEntity,
    NumberDeviceClass,
)
from homeassistant.config_entries import ConfigEntries
from homeassistant.const import UnitOfTemperature
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import IQStoveCoordinator


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntries.ConfigEntry,
    async_add_entities: AddEntitiesCallback,
):
    """Setup sensors from a config entry created in the integrations UI."""
    # get coordinator object from hass.data
    coordinator: IQStoveCoordinator = entry.runtime_data
    # create a IQStoveNumberEntity for _ledBri
    sensors = [IQstoveNumberEntity(coordinator, "_ledBri")]
    async_add_entities(sensors, update_before_add=True)


class IQstoveNumberEntity(CoordinatorEntity, NumberEntity):
    """Representation of a Sensor."""

    def __init__(self, coordinator: IQStoveCoordinator, cmd):
        """Pass coordinator to CoordinatorEntity."""
        super().__init__(coordinator)
        self.cmd = cmd
        self._attr_native_max_value = 100
        self._attr_native_min_value = 0

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        # set native value to latest value
        self._attr_native_value = self.coordinator.data[self.cmd]
        # tell homeassistant to update state
        self.async_write_ha_state()

    @property
    def name(self) -> str:
        """Return the name of the sensor."""
        if self.cmd == "_ledBri":
            return "LED Brightness"
        return "undefined"

    @property
    def native_value(self) -> int | float:
        """Return the state of the entity."""
        return float(self.coordinator.data[self.cmd])

    async def async_set_native_value(self, value: float) -> None:
        """Update the current value."""
        self.coordinator.stove.setValue(self.cmd, value)

    @property
    def unique_id(self) -> str:
        """Return unique id."""
        # All entities must have a unique id.  Think carefully what you want this to be as
        # changing it later will cause HA to create new entities.
        return f"{DOMAIN}-sensor-{self.cmd}"

    @property
    def device_info(self):
        """Return device information about this entity."""
        return {
            "identifiers": {
                # Unique identifiers within a specific domain
                (DOMAIN, self.coordinator.data["_oemser"])
            },
            "manufacturer": "Hase",
            "model": "Sila Plus" if self.coordinator.data["_oemdev"] == "6" else None,
            "model_id": self.coordinator.data["_oemdev"],
            "name": f"Stove {self.coordinator.data["_oemser"]}",
            "serial_number": self.coordinator.data["_oemser"],
            "sw_version": f"Wifi {self.coordinator.data["_wversion"]}",
            "hw_version": f"Controller {self.coordinator.data["_oemver"]}",
        }
