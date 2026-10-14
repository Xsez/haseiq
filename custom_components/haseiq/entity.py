"""Base entity for the Hase iQ integration."""

from __future__ import annotations

import json
from typing import Any

from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .coordinator import IQStoveCloudCoordinator, IQStoveCoordinator

MAX_STATE_LENGTH = 255

type IQStoveAnyCoordinator = IQStoveCoordinator | IQStoveCloudCoordinator


class IQStoveEntity(CoordinatorEntity[IQStoveAnyCoordinator]):
    """Entity bound to one stove.

    `key` makes the unique ID (`<serial>-<key>`). For Gen 2, `node` names the
    cloud node the entity reads; the entity is unavailable while that node's
    stream is down (short reconnects are bridged, see `cloud.DISCONNECT_GRACE`).
    """

    _attr_has_entity_name = True

    def __init__(
        self, coordinator: IQStoveAnyCoordinator, key: str, node: str | None = None
    ) -> None:
        """Initialize the entity."""
        super().__init__(coordinator)
        self._node = node
        self._attr_unique_id = f"{coordinator.serial}-{key}"
        self._attr_device_info = coordinator.device_info

    @property
    def available(self) -> bool:
        """Return True if the data this entity reads is current."""
        if not super().available:
            return False
        if self._node is not None and isinstance(
            self.coordinator, IQStoveCloudCoordinator
        ):
            return self.coordinator.client.connected.get(self._node, False)
        return True


def live_data(data: dict[str, Any] | None) -> dict[str, Any]:
    """Return the Gen 2 `liveData` dict (empty while the stove is off)."""
    live = (data or {}).get("liveData")
    return live if isinstance(live, dict) else {}


def raw_state(value: Any) -> tuple[Any, bool]:
    """Turn any raw value into a sensor state.

    Returns `(state, complete)`; `complete` is False when the state had to be
    shortened or converted and the original should be kept as an attribute.
    """
    if value is None or isinstance(value, (int, float)) and not isinstance(value, bool):
        return value, True
    if isinstance(value, bool):
        return ("on" if value else "off"), True
    if isinstance(value, str):
        return value[:MAX_STATE_LENGTH], len(value) <= MAX_STATE_LENGTH
    text = json.dumps(value, separators=(",", ":"), ensure_ascii=False)
    return text[:MAX_STATE_LENGTH], False
