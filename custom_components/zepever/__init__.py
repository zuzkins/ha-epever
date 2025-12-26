"""The Epever integration."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant

from .const import DOMAIN
from .coordinator import EpeverDataUpdateCoordinator

PLATFORMS: list[Platform] = [Platform.SENSOR]

type EpeverConfigEntry = ConfigEntry[EpeverDataUpdateCoordinator]


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
