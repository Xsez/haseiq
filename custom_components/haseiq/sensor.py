"""Platform for sensor integration."""

from __future__ import annotations

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
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
    # create a IQStoveSensor entity for all state commands except 'appErr'
    sensors = [
        IQstoveSensor(coordinator, cmd)
        for cmd in coordinator.stove.Commands.state
        if cmd != "appErr"
    ]
    async_add_entities(sensors, update_before_add=True)


class IQstoveSensor(CoordinatorEntity, SensorEntity):
    """Representation of a Sensor."""

    def __init__(self, coordinator: IQStoveCoordinator, cmd):
        """Pass coordinator to CoordinatorEntity."""
        super().__init__(coordinator)
        self.cmd = cmd
        if self.cmd == "appPhase":
            self.optionEnums = [
                "idle",
                "heating up",
                "burning",
                "add wood",
                "don't add wood",
            ]

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
        if self.cmd == "appT":
            return "Temperature"
        if self.cmd == "appPhase":
            return "Phase"
        if self.cmd == "appP":
            return "Performance"
        if self.cmd == "appAufheiz":
            return "Heating up"
        if self.cmd == "appErr":
            return "Error"
        return "undefined"

    @property
    def native_value(self) -> int | float:
        """Return the state of the entity."""
        # for appPhase return a string from optionsEnums
        if self.cmd == "appPhase":
            return self.optionEnums[int(self.coordinator.data[self.cmd])]
        return float(self.coordinator.data[self.cmd])

    @property
    def native_unit_of_measurement(self) -> str | None:
        """Return unit of measurment."""
        if self.cmd == "appT":
            return UnitOfTemperature.CELSIUS
        return None

    @property
    def state_class(self) -> str | None:
        """Return state class."""
        # https://developers.home-assistant.io/docs/core/entity/sensor/#available-state-classes
        if not self.cmd == "appPhase":
            return SensorStateClass.MEASUREMENT
        return None

    @property
    def device_class(self) -> str | None:
        """Return device class."""
        if self.cmd == "appT":
            return SensorDeviceClass.TEMPERATURE
        if self.cmd == "appPhase":
            return SensorDeviceClass.ENUM
        return None

    @property
    def options(self) -> str | None:
        """Return ENUM options."""
        if self.cmd == "appPhase":
            return ["idle", "heating up", "burning", "add wood", "don't add wood"]
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
            "model": "Sila Plus" if self.coordinator.data["_oemdev"] == "6" else None,
            "model_id": self.coordinator.data["_oemdev"],
            "name": f"Stove {self.coordinator.data["_oemser"]}",
            "serial_number": self.coordinator.data["_oemser"],
            "sw_version": f"Wifi {self.coordinator.data["_wversion"]}",
            "hw_version": f"Controller {self.coordinator.data["_oemver"]}",
        }