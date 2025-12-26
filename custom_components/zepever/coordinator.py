"""Data update coordinator for Epever integration."""

from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import (
    CONF_DEVICE_ADDRESS,
    CONF_DEVICE_PORT,
    CONF_UNIT_ID,
    DEFAULT_SCAN_INTERVAL,
    DEFAULT_UNIT_ID,
    DOMAIN,
)
from .epever_com import get_all_data

_LOGGER = logging.getLogger(__name__)


class EpeverDataUpdateCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Class to manage fetching Epever data."""

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
    ) -> None:
        """Initialize coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(seconds=DEFAULT_SCAN_INTERVAL),
            config_entry=entry,
        )
        self.host = entry.data[CONF_DEVICE_ADDRESS]
        self.port = entry.data[CONF_DEVICE_PORT]
        self.unit_id = entry.data.get(CONF_UNIT_ID, DEFAULT_UNIT_ID)

    async def _async_update_data(self) -> dict[str, Any]:
        """Fetch data from Epever device."""
        try:
            data = await self.hass.async_add_executor_job(
                get_all_data, self.host, self.port, self.unit_id
            )
            if data is None:
                raise UpdateFailed("Failed to retrieve data from device")
            return data
        except Exception as err:
            raise UpdateFailed(f"Error communicating with device: {err}") from err

