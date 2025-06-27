import logging
from typing import Dict

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.components import zeroconf
from homeassistant.const import CONF_DEVICE, CONF_HOST, CONF_URL
from homeassistant.core import callback
import homeassistant.helpers.config_validation as cv

from .const import DOMAIN
from .IQstove import IQstove, IQStoveConnectionError

_LOGGER = logging.getLogger(__name__)

SETUP_SCHEMA = vol.Schema(
    {
        vol.Required("host"): str,
    }
)


class HaseIQConfigFlow(config_entries.ConfigFlow, domain="haseiq"):
    """Handle a config flow for Hase iQ Stove."""

    VERSION = 1

    async def async_step_user(self, user_input=None):
        """Handle the initial step."""
        errors = {}

        if user_input is not None:
            # Validate the host format
            if not self._validate_host(user_input["host"]):
                errors["host"] = "invalid_host"
            else:
                try:
                    # Attempt connection
                    stove = IQstove(user_input["host"], 8080)
                    await stove.connect()
                    _LOGGER.debug(
                        "Successfully connected to stove at %s", user_input["host"]
                    )
                except IQStoveConnectionError:
                    errors["base"] = "connection_error"
                    _LOGGER.error(
                        "Failed to connect to stove at %s", user_input["host"]
                    )
                except Exception as e:
                    errors["base"] = "unknown_error"
                    _LOGGER.exception("Unexpected error during config flow: %s", e)

                if not errors:
                    # No errors, create config entry
                    return self.async_create_entry(
                        title="Hase iQ Stove", data=user_input
                    )

        return self.async_show_form(
            step_id="user",
            data_schema=SETUP_SCHEMA,
            errors=errors,
        )

    async def async_step_reconfigure(self, user_input=None):
        """Handle reconfiguration of an existing entry."""
        errors = {}

        # Get the current configuration
        current_config = (
            self.context.get("entry").data if self.context.get("entry") else {}
        )

        if user_input is not None:
            # Validate the host format
            if not self._validate_host(user_input["host"]):
                errors["host"] = "invalid_host"
            else:
                try:
                    # Attempt connection
                    stove = IQstove(user_input["host"], 8080)
                    await stove.connect()
                    _LOGGER.debug(
                        "Successfully connected to stove at %s", user_input["host"]
                    )
                except IQStoveConnectionError:
                    errors["base"] = "connection_error"
                    _LOGGER.error(
                        "Failed to connect to stove at %s", user_input["host"]
                    )
                except Exception as e:
                    errors["base"] = "unknown_error"
                    _LOGGER.exception("Unexpected error during reconfiguration: %s", e)

                if not errors:
                    # No errors, update the existing entry
                    self.context["entry"].data.update(user_input)
                    return self.async_create_entry(
                        title="Hase iQ Stove", data=user_input
                    )

        return self.async_show_form(
            step_id="reconfigure",
            data_schema=vol.Schema(
                {
                    vol.Required("host", default=current_config.get("host", "")): str,
                }
            ),
            errors=errors,
        )

    async def async_step_zeroconf(self, discovery_info: zeroconf):
        """Handle zeroconf discovery."""
        _LOGGER.debug("Zeroconf discovery info: %s", discovery_info)
        host = discovery_info.host
        # Optionally, check for unique properties in discovery_info.properties
        # Example: Only continue if the service name matches expected pattern
        # if not discovery_info.name.startswith("HaseIQ"):
        #     return self.async_abort(reason="not_haseiq_device")

        # Check if already configured
        await self.async_set_unique_id(discovery_info.properties.get("serial", host))
        self._abort_if_unique_id_configured()

        # Show confirmation form to user
        self.context["title_placeholders"] = {"host": host}
        return await self.async_step_confirm({"host": host})

    async def async_step_confirm(self, user_input=None):
        """Confirm adding the discovered device."""
        errors = {}
        host = self.context.get("title_placeholders", {}).get("host", "")

        if user_input is not None:
            try:
                stove = IQstove(user_input["host"], 8080)
                await stove.connect()
            except IQStoveConnectionError:
                errors["base"] = "connection_error"
            except Exception as e:
                errors["base"] = "unknown_error"
                _LOGGER.exception("Unexpected error during zeroconf confirm: %s", e)
            if not errors:
                return self.async_create_entry(title="Hase iQ Stove", data=user_input)

        return self.async_show_form(
            step_id="confirm",
            data_schema=vol.Schema({vol.Required("host", default=host): str}),
            errors=errors,
        )

    def _validate_host(self, host: str) -> bool:
        """Validate the host format."""
        import re

        # Simple regex for validating IP addresses or hostnames
        pattern = r"^(?:[0-9]{1,3}\.){3}[0-9]{1,3}$|^[a-zA-Z0-9.-]+$"
        return re.match(pattern, host) is not None
