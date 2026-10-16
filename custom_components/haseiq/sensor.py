"""Sensor platform for the Hase iQ integration."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
import logging
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory, UnitOfTemperature, UnitOfTime
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.util import dt as dt_util

from .const import GEN1, PHASES_GEN1, PHASES_GEN2
from .entity import (
    MAX_STATE_LENGTH,
    IQStoveAnyCoordinator,
    IQStoveEntity,
    app_data,
    live_data,
    raw_state,
    unix_time,
)

_LOGGER = logging.getLogger(__name__)

MAX_RAW_SENSORS = 200


@dataclass(frozen=True, kw_only=True)
class IQStoveSensorDescription(SensorEntityDescription):
    """Describes a stove sensor."""

    value_fn: Callable[[dict[str, Any]], Any]
    node: str | None = None


def _number(value: Any) -> int | float | None:
    """Return value as a number, or None if it is not numeric."""
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, (int, float)):
        return value
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _gen2_phase(data: dict[str, Any]) -> str | None:
    return PHASES_GEN2.get(_number(live_data(data).get("F")))


def _history(data: dict[str, Any]) -> dict[str, Any]:
    history = data.get("historienliste")
    return history if isinstance(history, dict) else {}


def _last_firing(data: dict[str, Any]) -> tuple[int, Any] | None:
    """Return `(start timestamp, seconds since start)` of the newest firing, if any.

    The stove updates the seconds every minute while it burns, so after the
    firing they hold its duration.
    """
    firings = [(int(key), value) for key, value in _history(data).items() if key.isdigit()]
    return max(firings, default=None)


def _datetime(value: Any) -> datetime | None:
    timestamp = unix_time(value)
    return datetime.fromtimestamp(timestamp, UTC) if timestamp is not None else None


def _last_firing_start(data: dict[str, Any]) -> datetime | None:
    last = _last_firing(data)
    return _datetime(last[0]) if last else None


def _last_firing_duration(data: dict[str, Any]) -> Any:
    last = _last_firing(data)
    return _number(last[1]) if last else None


def _log_entries(data: dict[str, Any]) -> list[tuple[int, str]]:
    """Return the stove's log as `(unix time, text)`, newest first."""
    logs = data.get("logs")
    if not isinstance(logs, dict):
        return []
    return sorted(
        ((int(key), str(text)) for key, text in logs.items() if key.isdigit()),
        reverse=True,
    )


def _firing(data: dict[str, Any]) -> dict[str, Any]:
    """Return the statistics of the newest firing (see the cloud coordinator)."""
    firing = data.get("firing")
    return firing if isinstance(firing, dict) else {}


GEN1_SENSORS: tuple[IQStoveSensorDescription, ...] = (
    IQStoveSensorDescription(
        key="temperature",
        translation_key="temperature",
        device_class=SensorDeviceClass.TEMPERATURE,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda data: _number(data.get("appT")),
    ),
    IQStoveSensorDescription(
        key="phase",
        translation_key="phase",
        device_class=SensorDeviceClass.ENUM,
        options=list(PHASES_GEN1.values()),
        value_fn=lambda data: PHASES_GEN1.get(_number(data.get("appPhase"))),
    ),
    IQStoveSensorDescription(
        key="performance",
        translation_key="performance",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda data: _number(data.get("appP")),
    ),
    IQStoveSensorDescription(
        key="heating_up",
        translation_key="heating_up",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda data: _number(data.get("appAufheiz")),
    ),
)

# Gen 2 temperatures (T, TQUER) arrive in whole degrees
GEN2_SENSORS: tuple[IQStoveSensorDescription, ...] = (
    IQStoveSensorDescription(
        key="temperature",
        translation_key="temperature",
        node="liveData",
        device_class=SensorDeviceClass.TEMPERATURE,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        suggested_display_precision=0,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda data: _number(live_data(data).get("T")),
    ),
    IQStoveSensorDescription(
        # TQUER ("T quer", T̄): the mean temperature, restarts with each load of wood
        key="load_average_temperature",
        translation_key="load_average_temperature",
        node="liveData",
        device_class=SensorDeviceClass.TEMPERATURE,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        suggested_display_precision=0,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda data: _number(live_data(data).get("TQUER")),
    ),
    IQStoveSensorDescription(
        # TC: hundredths of °C, rises slowly from room temperature while burning
        key="controller_temperature",
        translation_key="controller_temperature",
        node="liveData",
        device_class=SensorDeviceClass.TEMPERATURE,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        suggested_display_precision=1,
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda data: (
            tc / 100 if (tc := _number(live_data(data).get("TC"))) is not None else None
        ),
    ),
    IQStoveSensorDescription(
        key="phase",
        translation_key="phase",
        node="liveData",
        device_class=SensorDeviceClass.ENUM,
        options=list(PHASES_GEN2.values()),
        value_fn=_gen2_phase,
    ),
    IQStoveSensorDescription(
        key="performance",
        translation_key="performance",
        node="liveData",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda data: _number(live_data(data).get("P")),
    ),
    IQStoveSensorDescription(
        key="primary_air",
        translation_key="primary_air",
        node="liveData",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda data: _number(live_data(data).get("PL")),
    ),
    IQStoveSensorDescription(
        key="secondary_air",
        translation_key="secondary_air",
        node="liveData",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda data: _number(live_data(data).get("SL")),
    ),
    IQStoveSensorDescription(
        key="refuel",
        translation_key="refuel",
        node="liveData",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda data: _number(live_data(data).get("N")),
    ),
    IQStoveSensorDescription(
        # firings kept in the cloud (`count` of the firing list is not a total);
        # not TOTAL_INCREASING since the cloud may drop old firings
        key="firing_count",
        translation_key="firing_count",
        node="historienliste",
        state_class=SensorStateClass.TOTAL,
        value_fn=lambda data: _firing(data).get("count"),
    ),
    IQStoveSensorDescription(
        key="last_firing",
        translation_key="last_firing",
        node="historienliste",
        device_class=SensorDeviceClass.TIMESTAMP,
        value_fn=_last_firing_start,
    ),
    IQStoveSensorDescription(
        # the key keeps the unique ID of the entity from before the meaning was known
        key="last_firing_value",
        translation_key="firing_duration",
        node="historienliste",
        # no display precision: the frontend then shows durations as h/min/s
        device_class=SensorDeviceClass.DURATION,
        native_unit_of_measurement=UnitOfTime.SECONDS,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=_last_firing_duration,
    ),
    IQStoveSensorDescription(
        key="firing_max_temperature",
        translation_key="firing_max_temperature",
        node="historienliste",
        device_class=SensorDeviceClass.TEMPERATURE,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        suggested_display_precision=0,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda data: _firing(data).get("max_temperature"),
    ),
    IQStoveSensorDescription(
        key="firing_average_temperature",
        translation_key="firing_average_temperature",
        node="historienliste",
        device_class=SensorDeviceClass.TEMPERATURE,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        suggested_display_precision=0,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda data: _firing(data).get("average_temperature"),
    ),
    IQStoveSensorDescription(
        key="firing_wood_loads",
        translation_key="firing_wood_loads",
        node="historienliste",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda data: _firing(data).get("wood_loads"),
    ),
    IQStoveSensorDescription(
        key="last_connection",
        translation_key="last_connection",
        node="konstant_app",
        device_class=SensorDeviceClass.TIMESTAMP,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda data: _datetime(app_data(data).get("tsfc")),
    ),
    IQStoveSensorDescription(
        # the stove's address in its Wi-Fi; informative only, Gen 2 has no local API
        key="ip_address",
        translation_key="ip_address",
        node="konstant_app",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda data: app_data(data).get("ip") or None,
    ),
)

GEN2_LOG_SENSOR = IQStoveSensorDescription(
    key="last_log_entry",
    translation_key="last_log_entry",
    node="logs",
    entity_category=EntityCategory.DIAGNOSTIC,
    value_fn=lambda data: entries[0][1] if (entries := _log_entries(data)) else None,
)
LOG_LINES = 20  # log lines kept in the attributes of the log sensor

# Keys with a dedicated entity, per node; they get no raw sensor
GEN2_DEDICATED: dict[str, set[str]] = {
    "liveData": {"T", "TQUER", "TC", "F", "P", "PL", "SL", "N"},
    # l/s: the LED brightness numbers, u: the firmware update binary sensor
    "konstant": {"l", "s", "u"},
    # sensors (tsfc, ip), binary sensors (ping: online, bv: firing, f: firmware
    # update progress) and the app notification event (n)
    "konstant_app": {"ping", "tsfc", "ip", "bv", "f", "n"},
}
# Gen 2 nodes whose leaves become raw sensors (historienliste has its own)
GEN2_RAW_NODES = ("liveData", "konstant", "konstant_app")


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the sensors of a stove."""
    coordinator: IQStoveAnyCoordinator = entry.runtime_data

    if coordinator.generation == GEN1:
        async_add_entities(
            IQStoveSensor(coordinator, description) for description in GEN1_SENSORS
        )
        return

    async_add_entities(
        [IQStoveSensor(coordinator, description) for description in GEN2_SENSORS]
        + [IQStoveLogSensor(coordinator, GEN2_LOG_SENSOR)]
    )

    known: set[tuple[str, str]] = set()

    @callback
    def _async_add_raw_sensors() -> None:
        """Create a raw sensor for every new value the cloud delivered."""
        new: list[IQStoveRawSensor] = []
        for node in GEN2_RAW_NODES:
            paths = set(_leaf_paths(coordinator.data.get(node) if coordinator.data else None))
            paths -= GEN2_DEDICATED.get(node, set())
            for path in sorted(paths):
                if (node, path) in known:
                    continue
                if len(known) >= MAX_RAW_SENSORS:
                    _LOGGER.warning("Too many raw values, not adding %s %s", node, path)
                    continue
                known.add((node, path))
                new.append(_gen2_raw_sensor(coordinator, node, path))
        if new:
            async_add_entities(new)

    _async_add_raw_sensors()
    entry.async_on_unload(coordinator.async_add_listener(_async_add_raw_sensors))


def _leaf_paths(tree: Any, prefix: str = "") -> list[str]:
    """Return the slash-separated paths of all leaves of a nested dict."""
    if not isinstance(tree, dict):
        return [prefix] if prefix else []
    paths: list[str] = []
    for key, value in tree.items():
        paths += _leaf_paths(value, f"{prefix}/{key}" if prefix else str(key))
    return paths


def _get_path(tree: Any, path: str) -> Any:
    for key in path.split("/"):
        if not isinstance(tree, dict):
            return None
        tree = tree.get(key)
    return tree


def _gen2_raw_sensor(
    coordinator: IQStoveAnyCoordinator, node: str, path: str
) -> IQStoveRawSensor:
    name = {"liveData": "Live", "konstant": "Konstant", "konstant_app": "App"}[node]
    name = f"{name} {path}"
    current = _get_path((coordinator.data or {}).get(node), path)
    return IQStoveRawSensor(
        coordinator,
        f"raw-{node}-{path}",
        name,
        lambda data: _get_path(data.get(node), path),
        node=node,
        # unknown liveData keys are numeric samples; elsewhere go by the value
        numeric=node == "liveData" and current is None
        or _number(current) is not None and not isinstance(current, (bool, str)),
        category=None if node == "liveData" else EntityCategory.DIAGNOSTIC,
    )


class IQStoveSensor(IQStoveEntity, SensorEntity):
    """A stove sensor with a known meaning."""

    entity_description: IQStoveSensorDescription

    def __init__(
        self, coordinator: IQStoveAnyCoordinator, description: IQStoveSensorDescription
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, description.key, description.node)
        self.entity_description = description

    @property
    def native_value(self) -> Any:
        """Return the state of the sensor."""
        return self.entity_description.value_fn(self.coordinator.data or {})


class IQStoveLogSensor(IQStoveSensor):
    """The newest line of the stove's event log, earlier lines as attributes."""

    # the lines repeat with every new entry; keep them out of the database
    _unrecorded_attributes = frozenset({"lines"})

    @property
    def native_value(self) -> str | None:
        """Return the newest log text."""
        value = super().native_value
        return value[:MAX_STATE_LENGTH] if value is not None else None

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Return the time of the newest entry and the latest lines."""
        entries = _log_entries(self.coordinator.data or {})
        if not entries:
            return None
        lines = [
            f"{dt_util.as_local(dt_util.utc_from_timestamp(time)):%Y-%m-%d %H:%M:%S} {text}"
            for time, text in entries[:LOG_LINES]
        ]
        return {"time": dt_util.utc_from_timestamp(entries[0][0]), "lines": lines}


class IQStoveRawSensor(IQStoveEntity, SensorEntity):
    """A stove value of unknown meaning, exposed as-is for debugging."""

    def __init__(
        self,
        coordinator: IQStoveAnyCoordinator,
        key: str,
        name: str,
        value_fn: Callable[[dict[str, Any]], Any],
        *,
        node: str | None = None,
        numeric: bool = False,
        category: EntityCategory | None = EntityCategory.DIAGNOSTIC,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, key, node)
        self._value_fn = value_fn
        self._numeric = numeric
        self._attr_name = name
        self._attr_entity_category = category
        if numeric:
            self._attr_state_class = SensorStateClass.MEASUREMENT

    def _raw(self) -> Any:
        return self._value_fn(self.coordinator.data or {})

    @property
    def native_value(self) -> Any:
        """Return the raw value as state."""
        value = self._raw()
        if self._numeric:
            return _number(value) if not isinstance(value, str) else None
        return raw_state(value)[0]

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Keep the full raw value when the state cannot show it."""
        value = self._raw()
        if self._numeric:
            if value is None or _number(value) is not None and not isinstance(value, str):
                return None
            return {"raw": value}
        return None if raw_state(value)[1] else {"raw": value}
