"""Config flow for the Epever integration."""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.selector import (
    SelectOptionDict,
    SelectSelector,
    SelectSelectorConfig,
)

from .const import (
    CONF_DEVICE_ADDRESS,
    CONF_DEVICE_NAME,
    CONF_DEVICE_PORT,
    CONF_DEVICE_TYPE,
    DEFAULT_PORT,
    DEVICE_TYPE_HP,
    DEVICE_TYPES,
    DOMAIN,
)
from .epever_com import get_all_data
from .hp_com import get_hp_data

_LOGGER = logging.getLogger(__name__)

STEP_USER_DATA_SCHEMA = vol.Schema(
    {
        # No default: reading the wrong register map looks like a dead device.
        vol.Required(CONF_DEVICE_TYPE): SelectSelector(
            SelectSelectorConfig(
                options=[
                    SelectOptionDict(value=value, label=label)
                    for value, label in DEVICE_TYPES.items()
                ]
            )
        ),
        vol.Required(CONF_DEVICE_NAME): str,
        vol.Required(CONF_DEVICE_ADDRESS): str,
        vol.Required(CONF_DEVICE_PORT, default=DEFAULT_PORT): int,
    }
)


async def validate_input(hass: HomeAssistant, data: dict[str, Any]) -> dict[str, Any]:
    """Validate the user input allows us to connect.

    Data has the keys from STEP_USER_DATA_SCHEMA with values provided by the user.
    """
    get_data = (
        get_hp_data if data[CONF_DEVICE_TYPE] == DEVICE_TYPE_HP else get_all_data
    )
    # Test connection by trying to fetch data
    try:
        result = await hass.async_add_executor_job(
            get_data,
            data[CONF_DEVICE_ADDRESS],
            data[CONF_DEVICE_PORT],
        )
        if result is None:
            raise CannotConnect
    except Exception as err:
        _LOGGER.exception("Error connecting to device: %s", err)
        raise CannotConnect from err

    # Return info that you want to store in the config entry.
    return {"title": data[CONF_DEVICE_NAME]}


class ConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Epever."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle the initial step."""
        errors: dict[str, str] = {}
        if user_input is not None:
            try:
                info = await validate_input(self.hass, user_input)
            except CannotConnect:
                errors["base"] = "cannot_connect"
            except Exception:
                _LOGGER.exception("Unexpected exception")
                errors["base"] = "unknown"
            else:
                return self.async_create_entry(title=info["title"], data=user_input)

        return self.async_show_form(
            step_id="user", data_schema=STEP_USER_DATA_SCHEMA, errors=errors
        )


class CannotConnect(HomeAssistantError):
    """Error to indicate we cannot connect."""
