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
        error = False
        if info is not None:
            try:
                pass
                # stove = await IQstove("192.168.1.158")
                # serial = stove.serial
            except Exception as e:
                error = True
            if not error:
                self.data = info
                return self.async_create_entry(title="Hase iQ Stove", data=self.data)

        return self.async_show_form(step_id="user", data_schema=SETUP_SCHEMA)
