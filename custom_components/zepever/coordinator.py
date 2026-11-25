"""Data update coordinator for Epever integration."""

from __future__ import annotations

import asyncio
import logging
import time
from collections import deque
from datetime import timedelta
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .const import (
    CONF_DEVICE_ADDRESS,
    CONF_DEVICE_PORT,
    CONF_DEVICE_TYPE,
    CONF_UNIT_ID,
    CONNECTION_QUALITY_DEGRADED,
    CONNECTION_QUALITY_DEGRADED_RATE,
    CONNECTION_QUALITY_OFFLINE,
    CONNECTION_QUALITY_OK,
    CONNECTION_QUALITY_WINDOW,
    DEFAULT_SCAN_INTERVAL,
    DEFAULT_UNIT_ID,
    DEVICE_MODELS,
    DEVICE_TYPE_HP,
    DEVICE_TYPE_TRACER,
    DOMAIN,
    HP_ENERGY_INTERVAL,
    HP_ENERGY_RETRY_INTERVAL,
    HP_LOG_INTERVAL,
    HP_LOG_SIZE,
    HP_SCAN_INTERVAL,
    MAX_CONSECUTIVE_FAILURES,
    REACQUIRE_COOLDOWN_SECONDS,
)
from .epever_com import (
    force_mppt_reacquire,
    get_all_data,
    set_load_control_mode,
    set_manual_load_output,
)
from .hp_com import HP_ENERGY_BLOCKS, get_hp_data

_LOGGER = logging.getLogger(__name__)


class EpeverDataUpdateCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Class to manage fetching Epever data."""

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
    ) -> None:
        """Initialize coordinator."""
        self.device_type = entry.data.get(CONF_DEVICE_TYPE, DEVICE_TYPE_TRACER)
        is_hp = self.device_type == DEVICE_TYPE_HP
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(
                seconds=HP_SCAN_INTERVAL if is_hp else DEFAULT_SCAN_INTERVAL
            ),
            config_entry=entry,
        )
        self.host = entry.data[CONF_DEVICE_ADDRESS]
        self.port = entry.data[CONF_DEVICE_PORT]
        self.device_model = DEVICE_MODELS[self.device_type]
        self.unit_id = entry.data.get(CONF_UNIT_ID, DEFAULT_UNIT_ID)
        # The WiFi dongle handles one TCP client at a time; every Modbus
        # operation (poll or reacquire toggle) must hold this lock.
        self.modbus_lock = asyncio.Lock()
        self._last_reacquire: float | None = None
        self.consecutive_failures = 0
        # Outcome of the most recent polls (True = success) and the segment
        # of the last failure, for the connection quality sensor.
        self.recent_polls: deque[bool] = deque(maxlen=CONNECTION_QUALITY_WINDOW)
        self.last_failed_segment: str | None = None
        # (UTC time, {address: value}) of the HP register blocks, HP only.
        self.register_log: deque[tuple[str, dict[int, int]]] = deque(maxlen=HP_LOG_SIZE)
        self._last_register_log: float | None = None
        self._energy: dict[int, int] = {}
        # When each energy block is due, and why its last read failed.
        self._energy_due = dict.fromkeys(HP_ENERGY_BLOCKS, 0.0)
        self.energy_errors: dict[int, str] = {}

    async def _async_update_data(self) -> dict[str, Any]:
        """Fetch data from Epever device."""
        try:
            async with self.modbus_lock:
                if self.device_type == DEVICE_TYPE_HP:
                    data = await self._async_get_hp_data()
                else:
                    data = await self.hass.async_add_executor_job(
                        get_all_data, self.host, self.port, self.unit_id
                    )
            if data is None:
                raise UpdateFailed("Failed to retrieve data from device")
        except Exception as err:
            self.consecutive_failures += 1
            self.recent_polls.append(False)
            self.last_failed_segment = getattr(err, "segment", None)
            # Log every failure up to the threshold (the base coordinator
            # only logs the first) so the failing segments can be compared;
            # beyond it a sustained outage would flood the log.
            log = (
                _LOGGER.warning
                if self.consecutive_failures <= MAX_CONSECUTIVE_FAILURES
                else _LOGGER.debug
            )
            log(
                "Poll failed (%d/%d consecutive): %s",
                self.consecutive_failures,
                MAX_CONSECUTIVE_FAILURES,
                err,
            )
            if (
                self.data is not None
                and self.consecutive_failures < MAX_CONSECUTIVE_FAILURES
            ):
                return self.data
            raise UpdateFailed(f"Error communicating with device: {err}") from err
        self.consecutive_failures = 0
        self.recent_polls.append(True)
        if self.device_type == DEVICE_TYPE_HP:
            self._log_registers(data)
        return data

    async def _async_get_hp_data(self) -> dict[str, Any]:
        """Read the HP inverter, with at most one energy block that is due.

        One per poll bounds the time lost to unanswered reads, and keeps a
        silent block from hiding the others.
        """
        block: tuple[int, int] | None = None
        # Not on the first poll: an unanswered read must not delay the setup.
        if self.data is not None:
            block = min(HP_ENERGY_BLOCKS, key=self._energy_due.__getitem__)
            if self._energy_due[block] > time.monotonic():
                block = None
        data = await self.hass.async_add_executor_job(
            get_hp_data, self.host, self.port, self.unit_id, block
        )
        if block is not None:
            address = block[0]
            # Keep the last counters over a failed read.
            self._energy = {**self._energy, **data["energy"]}
            self._energy_due[block] = time.monotonic() + (
                HP_ENERGY_INTERVAL
                if address in self._energy
                else HP_ENERGY_RETRY_INTERVAL
            )
            if data["energy_error"] is None:
                self.energy_errors.pop(address, None)
            else:
                self.energy_errors[address] = data["energy_error"]
        return {"registers": data["registers"], "energy": self._energy}

    def _log_registers(self, data: dict[str, Any]) -> None:
        """Keep a register snapshot every HP_LOG_INTERVAL seconds."""
        now = time.monotonic()
        if (
            self._last_register_log is None
            or now - self._last_register_log >= HP_LOG_INTERVAL
        ):
            self._last_register_log = now
            self.register_log.append(
                (
                    dt_util.utcnow().isoformat(timespec="seconds"),
                    {**data["energy"], **data["registers"]},
                )
            )

    def _require_tracer(self) -> None:
        """Refuse writes to other devices: the Tracer registers mean other things."""
        if self.device_type != DEVICE_TYPE_TRACER:
            raise ServiceValidationError(
                f"Not supported on this device: {self.device_model}"
            )

    @property
    def recent_failure_rate(self) -> float:
        """Fraction of failed polls within the recent window."""
        if not self.recent_polls:
            return 0.0
        return self.recent_polls.count(False) / len(self.recent_polls)

    @property
    def connection_quality(self) -> str:
        """Summarize link health: offline, degraded or ok."""
        if not self.last_update_success:
            return CONNECTION_QUALITY_OFFLINE
        if (
            self.consecutive_failures
            or self.recent_failure_rate >= CONNECTION_QUALITY_DEGRADED_RATE
        ):
            return CONNECTION_QUALITY_DEGRADED
        return CONNECTION_QUALITY_OK

    async def async_force_mppt_reacquire(self, off_seconds: int) -> None:
        """Toggle charging off/on to provoke an MPPT re-sweep (experimental).

        Raises:
            ServiceValidationError: if triggered again within the cooldown.
            HomeAssistantError: if the toggle fails; the message says whether
                charging was left disabled.
        """
        self._require_tracer()
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

    async def async_set_load_control_mode(self, mode: int) -> None:
        """Set the controller load-control mode."""
        self._require_tracer()
        try:
            async with self.modbus_lock:
                await self.hass.async_add_executor_job(
                    set_load_control_mode,
                    self.host,
                    self.port,
                    self.unit_id,
                    mode,
                )
        except Exception as err:
            raise HomeAssistantError(f"Could not set load control mode: {err}") from err
        await self.async_request_refresh()

    async def async_set_manual_load_output(self, enabled: bool) -> None:
        """Set the manual load output."""
        self._require_tracer()
        try:
            async with self.modbus_lock:
                await self.hass.async_add_executor_job(
                    set_manual_load_output,
                    self.host,
                    self.port,
                    self.unit_id,
                    enabled,
                )
        except Exception as err:
            raise HomeAssistantError(f"Could not set manual load: {err}") from err
        await self.async_request_refresh()
