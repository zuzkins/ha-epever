"""The Epever integration."""

from __future__ import annotations

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import ATTR_DEVICE_ID, Platform
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import config_validation as cv, device_registry as dr
from homeassistant.helpers.typing import ConfigType

from .const import (
    ATTR_OFF_SECONDS,
    DEFAULT_OFF_SECONDS,
    DOMAIN,
    MAX_OFF_SECONDS,
    MIN_OFF_SECONDS,
    SERVICE_FORCE_MPPT_REACQUIRE,
)
from .coordinator import EpeverDataUpdateCoordinator

PLATFORMS: list[Platform] = [Platform.BUTTON, Platform.SENSOR]

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)

type EpeverConfigEntry = ConfigEntry[EpeverDataUpdateCoordinator]

SERVICE_FORCE_MPPT_REACQUIRE_SCHEMA = vol.Schema(
    {
        vol.Optional(ATTR_DEVICE_ID): cv.string,
        vol.Optional(ATTR_OFF_SECONDS, default=DEFAULT_OFF_SECONDS): vol.All(
            vol.Coerce(int), vol.Range(min=MIN_OFF_SECONDS, max=MAX_OFF_SECONDS)
        ),
    }
)


def _async_resolve_entry(hass: HomeAssistant, call: ServiceCall) -> EpeverConfigEntry:
    """Resolve the service call to a loaded config entry."""
    entries: list[EpeverConfigEntry] = hass.config_entries.async_loaded_entries(DOMAIN)
    if not entries:
        raise ServiceValidationError("No Epever device is set up")

    device_id: str | None = call.data.get(ATTR_DEVICE_ID)
    if device_id is None:
        if len(entries) > 1:
            raise ServiceValidationError(
                "Multiple Epever devices are set up; specify device_id"
            )
        return entries[0]

    device = dr.async_get(hass).async_get(device_id)
    if device is None:
        raise ServiceValidationError(f"Unknown device: {device_id}")
    for entry in entries:
        if entry.entry_id in device.config_entries:
            return entry
    raise ServiceValidationError(f"Device {device_id} is not an Epever device")


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Set up the Epever integration and register its services."""

    async def _handle_force_mppt_reacquire(call: ServiceCall) -> None:
        entry = _async_resolve_entry(hass, call)
        await entry.runtime_data.async_force_mppt_reacquire(
            call.data[ATTR_OFF_SECONDS]
        )

    hass.services.async_register(
        DOMAIN,
        SERVICE_FORCE_MPPT_REACQUIRE,
        _handle_force_mppt_reacquire,
        schema=SERVICE_FORCE_MPPT_REACQUIRE_SCHEMA,
    )

    return True


async def async_setup_entry(hass: HomeAssistant, entry: EpeverConfigEntry) -> bool:
    """Set up Epever from a config entry."""
    coordinator = EpeverDataUpdateCoordinator(hass, entry)
    await coordinator.async_config_entry_first_refresh()

    entry.runtime_data = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    return True


async def async_unload_entry(hass: HomeAssistant, entry: EpeverConfigEntry) -> bool:
    """Unload a config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
