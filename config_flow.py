"""Config flow for FMI (Finnish Meteorological Institute) integration."""

import fmi_weather_client as fmi_client
from fmi_weather_client.errors import ClientError, ServerError
import voluptuous as vol

from homeassistant import config_entries, core
from homeassistant.core import callback
from homeassistant.helpers import config_validation as cv

from . import base_unique_id

from .const import (
    _LOGGER,
    CONF_FMISID,
)


async def validate_user_config(hass: core.HomeAssistant, data):
    """Validate input configuration for FMI.

    Data contains Latitude / Longitude provided by user or from
    HASS default configuration.
    """
    fmsid = data[CONF_FMISID]

    errors = ""

    return {"place": "Hanko", "err": errors}


class FMIConfigFlowHandler(config_entries.ConfigFlow, domain="fmi"):
    """Config flow handler for FMI."""

    VERSION = 1
    CONNECTION_CLASS = config_entries.CONN_CLASS_CLOUD_POLL

    async def async_step_user(self, user_input=None):
        """Handle user step."""
        # Display an option for the user to provide Lat/Long for the integration
        errors = {}
        if user_input is not None:

            await self.async_set_unique_id(
                base_unique_id(user_input[CONF_FMISID])
            )
            self._abort_if_unique_id_configured()

            valid = await validate_user_config(self.hass, user_input)

            if valid.get("err", "") == "":
                return self.async_create_entry(title=valid["place"], data=user_input)

            errors["fmi"] = valid["err"]

        data_schema = vol.Schema(
            {
                vol.Required(CONF_FMISID, default=123456): int,
            }
        )

        return self.async_show_form(
            step_id="user",
            data_schema=data_schema,
            errors=errors,
        )
