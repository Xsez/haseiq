"""Platform for sensor integration."""

from __future__ import annotations

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.config_entries import ConfigEntries
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import IQStoveCoordinator


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntries.ConfigEntry,
    async_add_entities: AddEntitiesCallback,
):
    """Setup sensors from a config entry created in the integrations UI."""
    # print("Sensor Async Setup")
    coordinator: IQStoveCoordinator = hass.data[DOMAIN][config_entry.entry_id]
    sensors = [
        IQstoveBinarySensor(coordinator, cmd)
        for cmd in coordinator.stove.Commands.state
        if cmd == "appErr"
    ]
    async_add_entities(sensors, update_before_add=True)


class IQstoveBinarySensor(CoordinatorEntity, BinarySensorEntity):
    """Representation of a Sensor."""

    def __init__(self, coordinator: IQStoveCoordinator, cmd):
        """Pass coordinator to CoordinatorEntity."""
        super().__init__(coordinator)
        self.cmd = cmd
        # print(f"{cmd} sensor init")

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        # print("Sensor Handle Coordinator Update", self.coordinator.data)
        self._attr_native_value = self.coordinator.data[self.cmd]
        self.async_write_ha_state()

    @property
    def name(self) -> str:
        """Return the name of the sensor."""
        if self.cmd == "appErr":
            return "Error"
        return "undefined"

    @property
    def is_on(self) -> int | float:
        """Return the state of the entity."""
        # Using native value and native unit of measurement, allows you to change units
        # in Lovelace and HA will automatically calculate the correct value.
        return bool(int(float(self.coordinator.data[self.cmd])))

    @property
    def device_class(self) -> str | None:
        if self.cmd == "appErr":
            return BinarySensorDeviceClass.PROBLEM
        return None

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
            "model": self.coordinator.data["_oemdev"],
            "name": f"Stove {self.coordinator.data["_oemser"]}",
        }