"""The Epever integration."""

from __future__ import annotations

import voluptuous as vol
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import ATTR_DEVICE_ID, Platform
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.typing import ConfigType

from .const import (
    ATTR_OFF_SECONDS,
    CONF_DEVICE_TYPE,
    DEFAULT_OFF_SECONDS,
    DEVICE_TYPE_TRACER,
    DOMAIN,
    MAX_OFF_SECONDS,
    MIN_OFF_SECONDS,
    SERVICE_FORCE_MPPT_REACQUIRE,
)
from .coordinator import EpeverDataUpdateCoordinator
from .hp_sensor import HP_DEBUG_KEY_PREFIX, HP_SENSOR_DESCRIPTIONS

PLATFORMS: list[Platform] = [
    Platform.BINARY_SENSOR,
    Platform.BUTTON,
    Platform.SELECT,
    Platform.SENSOR,
    Platform.SWITCH,
]

# The other platforms write to the Tracer.
READ_ONLY_PLATFORMS: list[Platform] = [Platform.BINARY_SENSOR, Platform.SENSOR]

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


def _is_tracer(entry: EpeverConfigEntry) -> bool:
    """Return whether the entry is a Tracer charge controller."""
    return entry.data.get(CONF_DEVICE_TYPE, DEVICE_TYPE_TRACER) == DEVICE_TYPE_TRACER


def _platforms(entry: EpeverConfigEntry) -> list[Platform]:
    """Return the platforms the device type supports."""
    return PLATFORMS if _is_tracer(entry) else READ_ONLY_PLATFORMS


def _remove_stale_debug_entities(hass: HomeAssistant, entry: EpeverConfigEntry) -> None:
    """Remove debug sensors that were confirmed or dropped since."""
    prefix = f"{entry.entry_id}_{HP_DEBUG_KEY_PREFIX}"
    current = {f"{entry.entry_id}_{d.key}" for d in HP_SENSOR_DESCRIPTIONS}
    registry = er.async_get(hass)
    for entity in er.async_entries_for_config_entry(registry, entry.entry_id):
        if entity.unique_id.startswith(prefix) and entity.unique_id not in current:
            registry.async_remove(entity.entity_id)


def _async_resolve_entry(hass: HomeAssistant, call: ServiceCall) -> EpeverConfigEntry:
    """Resolve the service call to a loaded config entry."""
    entries: list[EpeverConfigEntry] = hass.config_entries.async_loaded_entries(DOMAIN)
    if not entries:
        raise ServiceValidationError("No Epever device is set up")

    device_id: str | None = call.data.get(ATTR_DEVICE_ID)
    if device_id is None:
        # Another device type must not make the only Tracer ambiguous.
        entries = [entry for entry in entries if _is_tracer(entry)] or entries
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
        await entry.runtime_data.async_force_mppt_reacquire(call.data[ATTR_OFF_SECONDS])

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

    if not _is_tracer(entry):
        _remove_stale_debug_entities(hass, entry)

    await hass.config_entries.async_forward_entry_setups(entry, _platforms(entry))

    return True


async def async_unload_entry(hass: HomeAssistant, entry: EpeverConfigEntry) -> bool:
    """Unload a config entry."""
    return await hass.config_entries.async_unload_platforms(entry, _platforms(entry))
