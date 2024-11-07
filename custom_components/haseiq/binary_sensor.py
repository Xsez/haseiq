"""Platform for sensor integration."""

from __future__ import annotations

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.config_entries import ConfigEntries
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.typing import ConfigType, DiscoveryInfoType

from .const import DOMAIN, SCAN_INTERVAL
from .IQstove import IQstove

# stove = IQstove("192.168.1.158")


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntries.ConfigEntry,
    async_add_entities,
) -> None:
    """Setup sensors from a config entry created in the integrations UI."""
    config = hass.data[DOMAIN][config_entry.entry_id]
    sensors = [errorBinarySensor()]
    async_add_entities(sensors, update_before_add=True)


def setup_platform(
    hass: HomeAssistant,
    config: ConfigType,
    add_entities: AddEntitiesCallback,
    discovery_info: DiscoveryInfoType | None = None,
) -> None:
    """Set up the sensor platform."""
    add_entities([errorBinarySensor()])


class errorBinarySensor(BinarySensorEntity):
    """Representation of a Sensor."""

    _attr_name = "IQStove Error"
    _attr_device_class = BinarySensorDeviceClass.PROBLEM
    _attr_unique_id = f"stove123+{_attr_name}"

    def update(self) -> None:
        """Fetch new state data for the sensor.

        This is the only method that should fetch new data for Home Assistant.
        """

        # self._attr_is_on = bool(int(stove.error))

    @property
    def device_info(self):
        """Return device information about this entity."""
        return {
            "identifiers": {
                # Unique identifiers within a specific domain
                (DOMAIN, 123)
            }
        }
