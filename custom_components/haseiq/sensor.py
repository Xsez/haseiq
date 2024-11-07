"""Platform for sensor integration."""

from __future__ import annotations

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntries
from homeassistant.const import PERCENTAGE, UnitOfTemperature
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.typing import ConfigType, DiscoveryInfoType
from homeassistant.helpers.update_coordinator import (
    CoordinatorEntity,
    DataUpdateCoordinator,
    UpdateFailed,
)

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
        IQstoveSensor(coordinator, cmd) for cmd in coordinator.stove.Commands.state
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
        # Using native value and native unit of measurement, allows you to change units
        # in Lovelace and HA will automatically calculate the correct value.
        # await self.coordinator.async_request_refresh()
        # print("Sensor Native Value", self.coordinator.data[self.cmd])
        # return float(self.coordinator.getValue("appT"))
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
            "model": self.coordinator.data["_oemdev"],
            "name": f"Stove {self.coordinator.data["_oemser"]}",
        }

    # @property
    # def device_info(self):
    #     """Return device information about this entity."""
    #     return {
    #         "identifiers": {
    #             # Unique identifiers within a specific domain
    #             (DOMAIN, 1234)
    #         },
    #         "manufacturer": "Hase",
    #         "model": 123,
    #         "name": "Stove 123",
    #     }


# # class phaseSensor(SensorEntity):
# #     """Phase Sensor."""

# #     _attr_name = "IQStove Phase"
# #     _attr_device_class = SensorDeviceClass.ENUM
# #     _attr_options = ["idle", "heating up", "burning", "add wood", "don't add wood"]
# #     _attr_unique_id = f"stove{stove.serial}+{_attr_name}"

# #     def update(self) -> None:
# #         """Fetch new state data for the sensor.

# #         This is the only method that should fetch new data for Home Assistant.
# #         """
# #         # phase = stove.phase
# #         # self._attr_native_value = self._attr_options[int(phase)]
# #         # if (int(phase) == 0):
# #         #     self._attr_icon = "mdi:fireplace-off"
# #         # else:
# #         #     self._attr_icon = "mdi:fireplace"

# #     @property
# #     def device_info(self):
# #         """Return device information about this entity."""
# #         return {
# #             "identifiers": {
# #                 # Unique identifiers within a specific domain
# #                 (DOMAIN, stove.serial)
# #             }
# #         }


# # class performanceSensor(SensorEntity):
# #     """Performance Sensor."""

# #     _attr_name = "IQStove Performance"
# #     _attr_native_unit_of_measurement = PERCENTAGE
# #     _attr_state_class = SensorStateClass.MEASUREMENT
# #     _attr_unique_id = f"stove{stove.serial}+{_attr_name}"
# #     _attr_icon = "mdi:gauge"

# #     def update(self) -> None:
# #         """Fetch new state data for the sensor.

# #         This is the only method that should fetch new data for Home Assistant.
# #         """

# #         # self._attr_native_value = stove.performance

# #     @property
# #     def device_info(self):
# #         """Return device information about this entity."""
# #         return {
# #             "identifiers": {
# #                 # Unique identifiers within a specific domain
# #                 (DOMAIN, stove.serial)
# #             }
# #         }


# # class heatingUpSensor(SensorEntity):
# #     """Performance Sensor."""

# #     _attr_name = "IQStove Heating Up"
# #     _attr_native_unit_of_measurement = PERCENTAGE
# #     _attr_state_class = SensorStateClass.MEASUREMENT
# #     _attr_unique_id = f"stove{stove.serial}+{_attr_name}"
# #     _attr_icon = "mdi:elevation-rise"

# #     def update(self) -> None:
# #         """Fetch new state data for the sensor.

# #         This is the only method that should fetch new data for Home Assistant.
# #         """

# #         # self._attr_native_value = stove.heatingPercentage

# #     @property
# #     def device_info(self):
# #         """Return device information about this entity."""
# #         return {
# #             "identifiers": {
# #                 # Unique identifiers within a specific domain
# #                 (DOMAIN, stove.serial)
# #             }
# #         }
