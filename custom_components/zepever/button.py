"""Button platform for Epever integration."""

from __future__ import annotations

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import CONF_DEVICE_NAME, DEFAULT_OFF_SECONDS, DOMAIN
from .coordinator import EpeverDataUpdateCoordinator


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Epever buttons from a config entry."""
    coordinator: EpeverDataUpdateCoordinator = entry.runtime_data

    async_add_entities([EpeverForceMpptReacquireButton(coordinator)])


class EpeverForceMpptReacquireButton(
    CoordinatorEntity[EpeverDataUpdateCoordinator], ButtonEntity
):
    """Button that toggles charging off/on to provoke an MPPT re-sweep.

    Experimental, see docs/epever_mppt_reacquire_experiment.md. Uses the
    default off-time; call the zepever.force_mppt_reacquire service to tune
    off_seconds.
    """

    _attr_has_entity_name = True
    _attr_name = "Force MPPT reacquire"

    def __init__(self, coordinator: EpeverDataUpdateCoordinator) -> None:
        """Initialize the button."""
        super().__init__(coordinator)
        self._attr_unique_id = (
            f"{coordinator.config_entry.entry_id}_force_mppt_reacquire"
        )
        device_name = coordinator.config_entry.data.get(CONF_DEVICE_NAME, "Epever")
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, coordinator.config_entry.entry_id)},
            name=device_name,
            manufacturer="Epever",
            model="Solar Charge Controller",
        )

    async def async_press(self) -> None:
        """Handle the button press."""
        await self.coordinator.async_force_mppt_reacquire(DEFAULT_OFF_SECONDS)
