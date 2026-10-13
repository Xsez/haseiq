"""Config flow for the Hase iQ integration."""

from __future__ import annotations

import asyncio
import logging
import re
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.const import CONF_HOST
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.service_info.zeroconf import ZeroconfServiceInfo

from .cloud import (
    FirebaseAuth,
    HaseCloudError,
    InvalidShareLink,
    IQstoveCloud,
    decode_share_link,
    serial_from_oven_id,
)
from .const import (
    CONF_GENERATION,
    CONF_OVEN_ID,
    CONF_REFRESH_TOKEN,
    CONF_SHARE_LINK,
    DOMAIN,
    GEN1,
    GEN2,
)
from .IQstove import IQstove

_LOGGER = logging.getLogger(__name__)

HOST_RE = re.compile(r"^(?:[0-9]{1,3}\.){3}[0-9]{1,3}$|^[a-zA-Z0-9.-]+$")
PROBE_TIMEOUT = 10  # seconds

GEN1_SCHEMA = vol.Schema({vol.Required(CONF_HOST): str})
GEN2_SCHEMA = vol.Schema({vol.Required(CONF_SHARE_LINK): str})


class CannotConnect(Exception):
    """The stove or the cloud could not be reached."""


class OvenNotFound(Exception):
    """The share link points to an oven the cloud does not know."""


class HaseIQConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Hase iQ stoves."""

    VERSION = 1
    MINOR_VERSION = 2

    def __init__(self) -> None:
        """Initialize the flow."""
        self._host: str | None = None

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Let the user pick the stove generation."""
        return self.async_show_menu(step_id="user", menu_options=["gen1", "gen2"])

    # ── Gen 1 (local) ───────────────────────────────────────────────────────────

    async def async_step_gen1(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Set up a Gen 1 stove by host."""
        errors: dict[str, str] = {}
        if user_input is not None:
            host = user_input[CONF_HOST].strip()
            serial = await self._async_try_gen1(host, errors)
            if serial:
                await self.async_set_unique_id(serial)
                self._abort_if_unique_id_configured(updates={CONF_HOST: host})
                return self.async_create_entry(
                    title=f"Stove {serial}",
                    data={CONF_GENERATION: GEN1, CONF_HOST: host},
                )
        return self.async_show_form(
            step_id="gen1",
            data_schema=self.add_suggested_values_to_schema(GEN1_SCHEMA, user_input),
            errors=errors,
        )

    async def async_step_zeroconf(
        self, discovery_info: ZeroconfServiceInfo
    ) -> ConfigFlowResult:
        """Handle a Gen 1 stove found via zeroconf."""
        host = discovery_info.host
        self._async_abort_entries_match({CONF_HOST: host})
        try:
            serial = await self._async_probe_gen1(host)
        except CannotConnect:
            return self.async_abort(reason="cannot_connect")
        await self.async_set_unique_id(serial)
        # A known stove with a new address: update it and reload.
        self._abort_if_unique_id_configured(updates={CONF_HOST: host})
        self._host = host
        self.context["title_placeholders"] = {"name": f"Stove {serial}"}
        return await self.async_step_zeroconf_confirm()

    async def async_step_zeroconf_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Confirm adding a discovered stove."""
        name = self.context["title_placeholders"]["name"]
        if user_input is not None:
            return self.async_create_entry(
                title=name, data={CONF_GENERATION: GEN1, CONF_HOST: self._host}
            )
        self._set_confirm_only()
        return self.async_show_form(
            step_id="zeroconf_confirm",
            description_placeholders={"name": name, "host": self._host or ""},
        )

    async def _async_try_gen1(self, host: str, errors: dict[str, str]) -> str | None:
        """Probe a host, filling `errors` on failure. Return the serial."""
        if not HOST_RE.match(host):
            errors[CONF_HOST] = "invalid_host"
            return None
        try:
            return await self._async_probe_gen1(host)
        except CannotConnect:
            errors["base"] = "cannot_connect"
        except Exception:
            _LOGGER.exception("Unexpected error while probing %s", host)
            errors["base"] = "unknown"
        return None

    async def _async_probe_gen1(self, host: str) -> str:
        """Connect to a Gen 1 stove and return its serial number."""
        stove = IQstove(host, 8080, session=async_get_clientsession(self.hass))
        try:
            async with asyncio.timeout(PROBE_TIMEOUT):
                await stove.connect()
                await stove.getValue("_oemser")
                while not stove.values.get("_oemser"):
                    await asyncio.sleep(0.1)
        except Exception as err:  # timeout, refused, websocket errors
            raise CannotConnect from err
        finally:
            await stove.close()
        return str(stove.values["_oemser"])

    # ── Gen 2 (cloud) ───────────────────────────────────────────────────────────

    async def async_step_gen2(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Set up a Gen 2 stove from its share link."""
        errors: dict[str, str] = {}
        if user_input is not None:
            result = await self._async_try_gen2(user_input[CONF_SHARE_LINK], errors)
            if result:
                oven_id, refresh_token = result
                serial = serial_from_oven_id(oven_id)
                await self.async_set_unique_id(serial)
                # Same stove with a new controller (new ovenID): update it.
                self._abort_if_unique_id_configured(updates={CONF_OVEN_ID: oven_id})
                return self.async_create_entry(
                    title=f"Stove {serial}",
                    data={
                        CONF_GENERATION: GEN2,
                        CONF_OVEN_ID: oven_id,
                        CONF_REFRESH_TOKEN: refresh_token,
                    },
                )
        return self.async_show_form(
            step_id="gen2",
            data_schema=self.add_suggested_values_to_schema(GEN2_SCHEMA, user_input),
            errors=errors,
        )

    async def _async_try_gen2(
        self, share_link: str, errors: dict[str, str]
    ) -> tuple[str, str] | None:
        """Decode and check a share link, filling `errors` on failure.

        Returns `(ovenID, refresh token)`.
        """
        try:
            oven_id = decode_share_link(share_link)
        except InvalidShareLink:
            errors[CONF_SHARE_LINK] = "invalid_share_link"
            return None
        try:
            return oven_id, await self._async_probe_gen2(oven_id)
        except OvenNotFound:
            errors["base"] = "oven_not_found"
        except CannotConnect:
            errors["base"] = "cannot_connect_cloud"
        except Exception:
            _LOGGER.exception("Unexpected error while checking a share link")
            errors["base"] = "unknown"
        return None

    async def _async_probe_gen2(self, oven_id: str) -> str:
        """Sign in and check the oven exists. Return the refresh token."""
        session = async_get_clientsession(self.hass)
        auth = FirebaseAuth(session)
        client = IQstoveCloud(session, oven_id, auth)
        try:
            konstant = await client.async_get(f"konstant/{oven_id}")
        except HaseCloudError as err:
            raise CannotConnect from err
        if konstant is None:
            raise OvenNotFound
        assert auth.refresh_token is not None
        return auth.refresh_token

    # ── reconfigure ─────────────────────────────────────────────────────────────

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Change the host (Gen 1) or share link (Gen 2) of a stove."""
        entry = self._get_reconfigure_entry()
        errors: dict[str, str] = {}
        is_gen2 = entry.data.get(CONF_GENERATION, GEN1) == GEN2

        if user_input is not None:
            if is_gen2:
                result = await self._async_try_gen2(user_input[CONF_SHARE_LINK], errors)
                if result:
                    oven_id, _refresh_token = result
                    await self.async_set_unique_id(serial_from_oven_id(oven_id))
                    self._abort_if_unique_id_mismatch(reason="wrong_device")
                    return self.async_update_reload_and_abort(
                        entry, data_updates={CONF_OVEN_ID: oven_id}
                    )
            else:
                host = user_input[CONF_HOST].strip()
                serial = await self._async_try_gen1(host, errors)
                if serial:
                    await self.async_set_unique_id(serial)
                    if entry.unique_id is not None:
                        self._abort_if_unique_id_mismatch(reason="wrong_device")
                    return self.async_update_reload_and_abort(
                        entry, unique_id=serial, data_updates={CONF_HOST: host}
                    )

        if is_gen2:
            schema = GEN2_SCHEMA
            suggested = user_input
        else:
            schema = GEN1_SCHEMA
            suggested = user_input or {CONF_HOST: entry.data.get(CONF_HOST, "")}
        return self.async_show_form(
            step_id="reconfigure",
            data_schema=self.add_suggested_values_to_schema(schema, suggested),
            errors=errors,
        )
