"""Data update coordinator for Epever integration."""

from __future__ import annotations

import asyncio
import logging
import time
from datetime import timedelta
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import (
    CONF_DEVICE_ADDRESS,
    CONF_DEVICE_PORT,
    CONF_UNIT_ID,
    DEFAULT_SCAN_INTERVAL,
    DEFAULT_UNIT_ID,
    DOMAIN,
    REACQUIRE_COOLDOWN_SECONDS,
)
from .epever_com import force_mppt_reacquire, get_all_data

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
        # The WiFi dongle handles one TCP client at a time; every Modbus
        # operation (poll or reacquire toggle) must hold this lock.
        self.modbus_lock = asyncio.Lock()
        self._last_reacquire: float | None = None

    async def _async_update_data(self) -> dict[str, Any]:
        """Fetch data from Epever device."""
        try:
            async with self.modbus_lock:
                data = await self.hass.async_add_executor_job(
                    get_all_data, self.host, self.port, self.unit_id
                )
            if data is None:
                raise UpdateFailed("Failed to retrieve data from device")
            return data
        except Exception as err:
            raise UpdateFailed(f"Error communicating with device: {err}") from err

    async def async_force_mppt_reacquire(self, off_seconds: int) -> None:
        """Toggle charging off/on to provoke an MPPT re-sweep (experimental).

        Raises:
            ServiceValidationError: if triggered again within the cooldown.
            HomeAssistantError: if the toggle fails; the message says whether
                charging was left disabled.
        """
        now = time.monotonic()
        if (
            self._last_reacquire is not None
            and now - self._last_reacquire < REACQUIRE_COOLDOWN_SECONDS
        ):
            remaining = REACQUIRE_COOLDOWN_SECONDS - (now - self._last_reacquire)
            raise ServiceValidationError(
                f"MPPT reacquire ran less than {REACQUIRE_COOLDOWN_SECONDS}s ago;"
                f" retry in {remaining:.0f}s"
            )
        # Claim the cooldown slot before the toggle so queued concurrent
        # calls are rejected instead of toggling back-to-back.
        self._last_reacquire = now
        try:
            async with self.modbus_lock:
                result = await self.hass.async_add_executor_job(
                    force_mppt_reacquire,
                    self.host,
                    self.port,
                    self.unit_id,
                    off_seconds,
                )
        except Exception as err:
            # Let a failed attempt be retried immediately; if charging was
            # left disabled the user must be able to re-run this right away.
            self._last_reacquire = None
            raise HomeAssistantError(f"MPPT reacquire failed: {err}") from err
        _LOGGER.info(
            "MPPT reacquire toggle done (tripped after %.1fs, dwell %ds): "
            "before=%s mid=%s after=%s",
            result["trip_seconds"],
            off_seconds,
            result["before"],
            result["mid"],
            result["after"],
        )
        await self.async_request_refresh()

