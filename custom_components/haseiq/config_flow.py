from typing import Dict

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.const import CONF_DEVICE, CONF_HOST, CONF_URL
import homeassistant.helpers.config_validation as cv

from .const import DOMAIN
from .IQstove import IQstove

SETUP_SCHEMA = vol.Schema({vol.Required(CONF_HOST): cv.string})


class haseiqConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Example config flow."""

    # The schema version of the entries that it creates
    # Home Assistant will call your migrate method if the version changes
    VERSION = 1

    async def async_step_user(self, info):
        errors: dict[str, str] = {}
        if info is not None:
            try:
                stove = IQstove(info["host"], 8080)
                await stove.connect()
            except Exception as e:
                print(e)
                errors["base"] = "Could not connect"
            if "base" not in errors:
                self.data = info
                return self.async_create_entry(title="Hase iQ Stove", data=self.data)

        return self.async_show_form(
            step_id="user", data_schema=SETUP_SCHEMA, errors=errors
        )