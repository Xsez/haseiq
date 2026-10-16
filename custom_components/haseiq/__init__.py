"""The Hase iQ integration."""

from __future__ import annotations

import contextlib
import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, EVENT_HOMEASSISTANT_STOP, Platform
from homeassistant.core import Event, HomeAssistant, callback
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .cloud import FirebaseAuth, HaseCloudError, IQstoveCloud
from .const import (
    CONF_GENERATION,
    CONF_KEEPALIVE_HELD,
    CONF_OVEN_ID,
    CONF_REFRESH_TOKEN,
    DOMAIN,
    GEN1,
    GEN2,
)
from .coordinator import IQStoveCloudCoordinator, IQStoveCoordinator
from .IQstove import IQstove

_LOGGER = logging.getLogger(__name__)
PLATFORMS: list[Platform] = [
    Platform.BINARY_SENSOR,
    Platform.EVENT,
    Platform.NUMBER,
    Platform.SENSOR,
]

# Gen 1 unique IDs before 0.4 were `haseiq-sensor-<device key>`, the same for
# every stove. They are migrated to `<serial>-<key>`.
LEGACY_GEN1_KEYS = {
    "appT": "temperature",
    "appPhase": "phase",
    "appP": "performance",
    "appAufheiz": "heating_up",
    "appErr": "error",
    "_ledBri": "led_brightness",
}
# Gen 1 raw statistics sensors of 0.4.0b1, dropped again
REMOVED_GEN1_KEYS = ("appPTx", "appP30Tx", "appIQDarst", "appPT", "appP30T")
# Gen 2 raw sensors of earlier betas: liveData keys that do not exist (B, S) or
# now have a dedicated entity (F: phase, TQUER/TC: temperatures, l/s: LED
# numbers, u/f: firmware update, ping: online, tsfc: last connection,
# ip: IP address, bv: firing, n: app notification)
REMOVED_GEN2_KEYS = (
    "raw-liveData-B",
    "raw-liveData-F",
    "raw-liveData-S",
    "raw-liveData-TQUER",
    "raw-liveData-TC",
    "raw-konstant-l",
    "raw-konstant-s",
    "raw-konstant-u",
    "raw-konstant_app-bv",
    "raw-konstant_app-f",
    "raw-konstant_app-ip",
    "raw-konstant_app-n",
    "raw-konstant_app-ping",
    "raw-konstant_app-tsfc",
)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up a stove from a config entry."""
    session = async_get_clientsession(hass)
    coordinator: IQStoveCoordinator | IQStoveCloudCoordinator

    if entry.data.get(CONF_GENERATION, GEN1) == GEN2:

        @callback
        def _store_refresh_token(token: str) -> None:
            hass.config_entries.async_update_entry(
                entry, data={**entry.data, CONF_REFRESH_TOKEN: token}
            )

        auth = FirebaseAuth(
            session, entry.data.get(CONF_REFRESH_TOKEN), _store_refresh_token
        )
        client = IQstoveCloud(session, entry.data[CONF_OVEN_ID], auth)
        coordinator = IQStoveCloudCoordinator(hass, entry, client)
    else:
        stove = IQstove(entry.data[CONF_HOST], 8080, session=session)
        coordinator = IQStoveCoordinator(hass, entry, stove)

    try:
        await coordinator.async_config_entry_first_refresh()
    except Exception:
        # Keep the keep-alive (if taken); the next attempt reuses it.
        await coordinator.async_close(release=False)
        raise

    if coordinator.generation == GEN1:
        _async_migrate_gen1(hass, entry, coordinator.serial)
    else:
        _async_remove_entities(hass, coordinator.serial, REMOVED_GEN2_KEYS)

    entry.runtime_data = coordinator

    async def _async_on_stop(_event: Event) -> None:
        # Home Assistant does not unload entries on shutdown. Close the
        # connections but keep the keep-alive for the next start.
        await coordinator.async_close(release=False)

    entry.async_on_unload(
        hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STOP, _async_on_stop)
    )
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded:
        await entry.runtime_data.async_close(release=True)
    return unloaded


async def async_remove_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Give back a keep-alive count left by an entry that was not loaded.

    A loaded entry releases it on unload. One stuck in setup retry still holds
    it (setup keeps it for the next attempt) and is never unloaded.
    """
    if entry.data.get(CONF_GENERATION) != GEN2 or not entry.data.get(CONF_KEEPALIVE_HELD):
        return
    session = async_get_clientsession(hass)
    auth = FirebaseAuth(session, entry.data.get(CONF_REFRESH_TOKEN))
    client = IQstoveCloud(session, entry.data[CONF_OVEN_ID], auth)
    with contextlib.suppress(HaseCloudError):
        await client.async_add_keepalive(-1)


async def async_migrate_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Migrate old config entries."""
    if entry.version > 1:
        return False
    if entry.minor_version < 2:
        # 1.1 entries are all Gen 1
        hass.config_entries.async_update_entry(
            entry, data={CONF_GENERATION: GEN1, **entry.data}, minor_version=2
        )
    return True


@callback
def _async_remove_entities(hass: HomeAssistant, serial: str, keys: tuple[str, ...]) -> None:
    """Remove sensors of a stove that are no longer created."""
    registry = er.async_get(hass)
    for key in keys:
        if entity_id := registry.async_get_entity_id("sensor", DOMAIN, f"{serial}-{key}"):
            registry.async_remove(entity_id)


@callback
def _async_migrate_gen1(hass: HomeAssistant, entry: ConfigEntry, serial: str) -> None:
    """Give a Gen 1 entry and its entities serial-based unique IDs.

    Only the unique IDs change; entity IDs, history and customizations stay.
    Entities that were dropped again are removed.
    """
    if not serial:
        return
    # Old entries have no unique ID, or the host when added via zeroconf.
    if entry.unique_id != serial and not any(
        other.unique_id == serial
        for other in hass.config_entries.async_entries(DOMAIN)
    ):
        hass.config_entries.async_update_entry(entry, unique_id=serial)

    _async_remove_entities(hass, serial, REMOVED_GEN1_KEYS)
    registry = er.async_get(hass)
    for entity in er.async_entries_for_config_entry(registry, entry.entry_id):
        legacy_key = entity.unique_id.removeprefix(f"{DOMAIN}-sensor-")
        if legacy_key == entity.unique_id or legacy_key not in LEGACY_GEN1_KEYS:
            continue
        new_unique_id = f"{serial}-{LEGACY_GEN1_KEYS[legacy_key]}"
        if registry.async_get_entity_id(entity.domain, DOMAIN, new_unique_id):
            _LOGGER.warning(
                "Cannot migrate %s, unique ID %s is taken", entity.entity_id, new_unique_id
            )
            continue
        _LOGGER.info("Migrating %s to unique ID %s", entity.entity_id, new_unique_id)
        registry.async_update_entity(entity.entity_id, new_unique_id=new_unique_id)
