"""Simple Modbus communication for Epever devices."""

import logging
import time
from typing import Any

from pymodbus import FramerType
from pymodbus.client import ModbusTcpClient

_LOGGER = logging.getLogger(__name__)

# Magic init sequence required by the Epever WiFi dongle after connect,
# before any read/write.
_INIT_SEQUENCE = bytes.fromhex("20020000")

# Controller inner temperature upper limit (x100 °C). Lowering it below the
# actual controller temperature fakes an over-temperature condition: the
# protection loop (evaluated roughly every 10 s) halts PV production and
# releases the array to open-circuit voltage; restoring the original value
# clears the fault and the controller re-engages with a fresh MPPT sweep
# (~30-60 s). Verified on the test device 2026-07-03. The documented coil 0
# "charging device on/off" and 0x901B (power component limit, works on BN
# units) are both no-ops on Tracer AN hardware — see
# docs/epever_mppt_reacquire_experiment.md.
TEMP_LIMIT_REGISTER = 0x9019
TEMP_LIMIT_DISABLE_VALUE = 1000  # 10.00 °C
TEMP_LIMIT_DEFAULT = 8500  # 85.00 °C factory default, probe-confirmed
_TEMP_LIMIT_SANE_RANGE = (6000, 10000)

# Discrete input: "over temperature inside the device" — flips on when the
# protection trips, cleanly and irradiance-independently.
OVER_TEMP_FLAG_ADDRESS = 0x2000

_TRIP_TIMEOUT_SECONDS = 30
_TRIP_POLL_SECONDS = 2
_RESTORE_ATTEMPTS = 5


def get_pv_voltage(
    host: str, port: int, unit_id: int = 1
) -> float | None:
    """Retrieve the current PV voltage from the Epever device over Modbus TCP.

    Args:
        host: IP address of the Epever device.
        port: Modbus TCP port of the device.
        unit_id: Modbus unit ID of the device.

    Returns:
        PV voltage in volts, or None if an error occurs.
    """
    # Use RTU framer over TCP if available (as per Epever protocol)
    client = ModbusTcpClient(host=host, port=port, retries=1, framer=FramerType.RTU)

    try:
        if not client.connect():
            return None

        # Send initialization sequence (required by Epever devices)
        client.send(_INIT_SEQUENCE)

        # Read input register 0x3100 for PV voltage
        result = client.read_input_registers(address=0x3100, count=19)

        if result.isError():
            return None

        # PV voltage is scaled by dividing by 100 (register value / 100 = volts)
        return result.registers[0] / 100.0

    except (ConnectionError, TimeoutError, ValueError):
        return None
    finally:
        client.close()


def _value16(value: int) -> float:
    """Convert 16-bit signed value to float, scaled by 100."""
    return (value if value < 32768 else value - 65536) / 100.0


def _value32(low: int, high: int) -> float:
    """Convert 32-bit signed value to float, scaled by 100."""
    combined = low + (high << 16)
    return (combined if combined < 2147483648 else combined - 4294967296) / 100.0


def get_all_data(
    host: str, port: int, unit_id: int = 1
) -> dict[str, Any] | None:
    """Retrieve all data from the Epever device over Modbus TCP.

    Args:
        host: IP address of the Epever device.
        port: Modbus TCP port of the device.
        unit_id: Modbus unit ID of the device.

    Returns:
        Dictionary with all device data, or None if an error occurs.
    """
    client = ModbusTcpClient(host=host, port=port, retries=1, framer=FramerType.RTU)

    try:
        if not client.connect():
            return None

        # Send initialization sequence (required by Epever devices)
        client.send(_INIT_SEQUENCE)

        data: dict[str, Any] = {}

        # Read realtime data registers 0x3100 - 0x3112 (count=19). Some
        # Epever firmware silently truncates the response past this window
        # (observed: a count=27 read returns only 19 registers), so we keep
        # this read small and fetch later registers separately.
        result = client.read_input_registers(
            address=0x3100, count=19, device_id=unit_id
        )
        if not result.isError() and len(result.registers) >= 19:
            registers = result.registers

            # PV array data (offset from 0x3100)
            data["pv_voltage"] = _value16(registers[0])  # 0x3100
            data["pv_current"] = _value16(registers[1])  # 0x3101
            data["pv_power"] = _value32(registers[2], registers[3])  # 0x3102-0x3103

            # Battery data
            data["battery_voltage"] = _value16(registers[4])  # 0x3104
            data["battery_current"] = _value16(registers[5])  # 0x3105
            data["battery_power"] = _value32(
                registers[6], registers[7]
            )  # 0x3106-0x3107
            # Internal battery sensor on the controller body.
            data["internal_battery_temperature"] = _value16(registers[16])  # 0x3110

            # Load data
            data["load_voltage"] = _value16(registers[12])  # 0x310C
            data["load_current"] = _value16(registers[13])  # 0x310D
            data["load_power"] = _value32(registers[14], registers[15])  # 0x310E-0x310F

            # Device temperature
            data["device_temperature"] = _value16(registers[17])  # 0x3111

        # Next batch of realtime data, fetched in a separate transaction
        # because some firmware can't serve it together with the earlier
        # block (see comment above). Tolerate failure so other sensors
        # still come online on firmware variants that don't support it.
        result = client.read_input_registers(
            address=0x311A, count=2, device_id=unit_id
        )
        if not result.isError() and len(result.registers) >= 2:
            soc = result.registers[0]  # 0x311A, percentage with no scaling
            if 0 <= soc <= 100:
                data["battery_state_of_charge"] = soc
            # The firmware returns a sentinel value (commonly 0) when no
            # RTS probe is connected. We have no reliable way to distinguish
            # that from a valid reading at the same temperature, so the
            # value is exposed as-is and only obviously bogus readings are
            # rejected by a wide sanity range.
            remote_temp = _value16(result.registers[1])
            if -100 <= remote_temp <= 150:
                data["remote_battery_temperature"] = remote_temp

        # Read status registers (0x3200 - 0x3202)
        result = client.read_input_registers(address=0x3200, count=3, device_id=unit_id)
        if not result.isError():
            status_registers = result.registers

            # Battery status (0x3200)
            battery_status_value = status_registers[0]
            battery_status = {
                "running": bool(battery_status_value & 0x0001),
                "fault": bool((battery_status_value >> 1) & 0x0001),
                "charging_equipment_overvoltage": bool(
                    (battery_status_value >> 2) & 0x0001
                ),
                "charging_equipment_short_circuit": bool(
                    (battery_status_value >> 3) & 0x0001
                ),
                "charging_equipment_overcurrent": bool(
                    (battery_status_value >> 4) & 0x0001
                ),
                "charging_equipment_overheating": bool(
                    (battery_status_value >> 5) & 0x0001
                ),
                "charging_equipment_short_circuit_2": bool(
                    (battery_status_value >> 6) & 0x0001
                ),
                "battery_overvoltage": bool((battery_status_value >> 7) & 0x0001),
                "battery_under voltage": bool((battery_status_value >> 8) & 0x0001),
            }
            # data["battery_status"] = battery_status

            # Charging equipment status (0x3201)
            charging_status_value = status_registers[1]
            charging_status = {
                "running": bool(charging_status_value & 0x0001),
                "fault": bool((charging_status_value >> 1) & 0x0001),
                "input_overvoltage": bool((charging_status_value >> 2) & 0x0001),
                "input_undervoltage": bool((charging_status_value >> 3) & 0x0001),
                "input_overcurrent": bool((charging_status_value >> 4) & 0x0001),
                "output_overvoltage": bool((charging_status_value >> 5) & 0x0001),
                "output_short_circuit": bool((charging_status_value >> 6) & 0x0001),
                "mosfet_short_circuit": bool((charging_status_value >> 7) & 0x0001),
                "overheating": bool((charging_status_value >> 8) & 0x0001),
            }
            # data["charging_equipment_status"] = charging_status

            # Discharging equipment status (0x3202)
            discharging_status_value = status_registers[2]
            discharging_status = {
                "running": bool(discharging_status_value & 0x0001),
                "fault": bool((discharging_status_value >> 1) & 0x0001),
                "input_voltage_abnormal": bool(
                    (discharging_status_value >> 8) & 0x0001
                ),
                "output_overvoltage": bool((discharging_status_value >> 4) & 0x0001),
                "output_short_circuit": bool((discharging_status_value >> 11) & 0x0001),
                "overload": bool((discharging_status_value >> 12) & 0x0003),
            }
            # data["discharging_equipment_status"] = discharging_status

        # All energy counters (0x3304 - 0x3313) in one read. 32-bit values
        # in consecutive lo/hi pairs, scaled by 100 (kWh). 0x3300-0x3303
        # carry today's voltage min/max stats which we skip.
        result = client.read_input_registers(
            address=0x3304, count=16, device_id=unit_id
        )
        if not result.isError() and len(result.registers) >= 16:
            er = result.registers

            # Consumed energy (load)
            data["consumed_energy_today"] = _value32(er[0], er[1])  # 0x3304-0x3305
            data["consumed_energy_this_month"] = _value32(er[2], er[3])  # 0x3306-0x3307
            data["consumed_energy_this_year"] = _value32(er[4], er[5])  # 0x3308-0x3309
            data["total_consumed_energy"] = _value32(er[6], er[7])  # 0x330A-0x330B

            # Generated energy (PV)
            data["generated_energy_today"] = _value32(er[8], er[9])  # 0x330C-0x330D
            data["generated_energy_this_month"] = _value32(er[10], er[11])  # 0x330E-0x330F
            data["generated_energy_this_year"] = _value32(er[12], er[13])  # 0x3310-0x3311
            data["total_generated_energy"] = _value32(er[14], er[15])  # 0x3312-0x3313

        # Live battery temperature (RTS-aware, falls back to internal sensor
        # or a 25.00 °C sentinel when no source is wired) and ambient
        # temperature from the controller's statistical block.
        result = client.read_input_registers(
            address=0x331D, count=2, device_id=unit_id
        )
        if not result.isError() and len(result.registers) >= 2:
            data["battery_temperature"] = _value16(result.registers[0])  # 0x331D
            data["ambient_temperature"] = _value16(result.registers[1])  # 0x331E

        return data

    except (ConnectionError, TimeoutError, ValueError, IndexError):
        return None
    finally:
        client.close()


def _pv_snapshot(client: ModbusTcpClient, unit_id: int) -> dict[str, float] | None:
    """Read PV voltage/current/power for before/after experiment logging."""
    try:
        result = client.read_input_registers(address=0x3100, count=4, device_id=unit_id)
    except (ConnectionError, TimeoutError, ValueError):
        return None
    if result.isError() or len(result.registers) < 4:
        return None
    registers = result.registers
    return {
        "pv_voltage": _value16(registers[0]),
        "pv_current": _value16(registers[1]),
        "pv_power": _value32(registers[2], registers[3]),
    }


def _read_temp_limit(client: ModbusTcpClient, unit_id: int) -> int | None:
    """Read the raw controller inner temperature upper limit register."""
    try:
        result = client.read_holding_registers(
            address=TEMP_LIMIT_REGISTER, count=1, device_id=unit_id
        )
    except (ConnectionError, TimeoutError, ValueError):
        return None
    if result.isError() or len(result.registers) < 1:
        return None
    return result.registers[0]


def _over_temp_tripped(client: ModbusTcpClient, unit_id: int) -> bool | None:
    """Read the over-temperature discrete input; None if unreadable."""
    try:
        result = client.read_discrete_inputs(
            address=OVER_TEMP_FLAG_ADDRESS, count=1, device_id=unit_id
        )
    except (ConnectionError, TimeoutError, ValueError):
        return None
    if result.isError() or not result.bits:
        return None
    return result.bits[0]


def _restore_temp_limit(client: ModbusTcpClient, unit_id: int, value: int) -> None:
    """Write the temperature limit back and verify by readback, retrying hard.

    Production is halted when this is called; giving up leaves the
    controller convinced it is overheating (persists across reboots), so
    retry with reconnects and catch everything in between attempts. A write
    ACK alone is not trusted — this firmware echoes writes it ignores — so
    every attempt is verified with a readback.
    """
    last_error: BaseException | str | None = None
    for attempt in range(1, _RESTORE_ATTEMPTS + 1):
        try:
            if not client.connect():
                raise ConnectionError("reconnect failed")
            result = client.write_register(
                TEMP_LIMIT_REGISTER, value, device_id=unit_id
            )
            if result.isError():
                last_error = str(result)
            else:
                readback = _read_temp_limit(client, unit_id)
                if readback == value:
                    if attempt > 1:
                        _LOGGER.warning(
                            "Temperature limit restored on attempt %d/%d",
                            attempt,
                            _RESTORE_ATTEMPTS,
                        )
                    return
                last_error = f"readback {readback} != {value}"
        except Exception as err:  # noqa: BLE001 - must keep retrying
            last_error = err
            # Force a fresh connection (and re-init) for the next attempt.
            client.close()
            if client.connect():
                client.send(_INIT_SEQUENCE)
        _LOGGER.warning(
            "Restore temperature limit attempt %d/%d failed: %s",
            attempt,
            _RESTORE_ATTEMPTS,
            last_error,
        )
        time.sleep(1)
    raise RuntimeError(
        f"PV PRODUCTION IS STILL HALTED: could not restore holding register "
        f"0x{TEMP_LIMIT_REGISTER:04X} to {value} after {_RESTORE_ATTEMPTS} "
        f"attempts (last error: {last_error}). The controller thinks it is "
        f"overheating and this persists across reboots — write {value} to "
        f"0x{TEMP_LIMIT_REGISTER:04X} manually to recover."
    )


def force_mppt_reacquire(
    host: str, port: int, unit_id: int = 1, off_seconds: int = 5
) -> dict[str, Any]:
    """Briefly halt PV production to provoke an MPPT re-sweep.

    Lowers the controller inner temperature upper limit (0x9019) to fake an
    over-temperature condition, waits for the protection to trip (the
    firmware evaluates it roughly every 10 s), dwells off_seconds in the
    halted state, then restores the original value. The controller
    re-engages with a fresh MPPT sweep within ~a minute of the restore.
    Experimental, see docs/epever_mppt_reacquire_experiment.md. Holds a
    single connection for the whole toggle so a reconnect failure mid-window
    cannot strand the controller in the halted state. The register is
    flash-backed: intended for sporadic manual use, not tight loops.

    Returns:
        Dict with the original limit, seconds until the protection tripped,
        and "before"/"mid"/"after" PV snapshots (snapshots may be None).

    Raises:
        ConnectionError: if the device is unreachable.
        RuntimeError: if a write fails or the protection never trips; the
            message says whether the temperature limit was left lowered.
    """
    client = ModbusTcpClient(host=host, port=port, retries=1, framer=FramerType.RTU)
    try:
        if not client.connect():
            raise ConnectionError(f"Could not connect to {host}:{port}")
        client.send(_INIT_SEQUENCE)

        original = _read_temp_limit(client, unit_id)
        if original is None:
            raise RuntimeError(
                f"Could not read holding register 0x{TEMP_LIMIT_REGISTER:04X}; "
                f"aborting (nothing was written)"
            )
        if original == TEMP_LIMIT_DISABLE_VALUE:
            # Leftover from a previous toggle that failed to restore.
            _LOGGER.warning(
                "0x%04X reads the disable value %d - previous toggle did not "
                "restore; using the factory default %d as restore target",
                TEMP_LIMIT_REGISTER,
                TEMP_LIMIT_DISABLE_VALUE,
                TEMP_LIMIT_DEFAULT,
            )
            original = TEMP_LIMIT_DEFAULT
        elif not _TEMP_LIMIT_SANE_RANGE[0] <= original <= _TEMP_LIMIT_SANE_RANGE[1]:
            raise RuntimeError(
                f"0x{TEMP_LIMIT_REGISTER:04X} reads {original}, outside the "
                f"sane range {_TEMP_LIMIT_SANE_RANGE}; refusing to touch it "
                f"(nothing was written)"
            )

        before = _pv_snapshot(client, unit_id)

        result = client.write_register(
            TEMP_LIMIT_REGISTER, TEMP_LIMIT_DISABLE_VALUE, device_id=unit_id
        )
        if result.isError():
            raise RuntimeError(
                f"Device rejected the disable write (temperature limit "
                f"unchanged): {result}"
            )
        _LOGGER.info(
            "Temperature limit lowered to %d (original %d, before: %s); "
            "waiting for the protection to trip",
            TEMP_LIMIT_DISABLE_VALUE,
            original,
            before,
        )

        mid = None
        trip_seconds: float | None = None
        try:
            readback = _read_temp_limit(client, unit_id)
            if readback != TEMP_LIMIT_DISABLE_VALUE:
                raise RuntimeError(
                    f"Disable write did not stick: 0x{TEMP_LIMIT_REGISTER:04X} "
                    f"reads {readback} after writing {TEMP_LIMIT_DISABLE_VALUE}"
                )
            # The protection loop only evaluates every ~10 s; poll the
            # over-temperature flag instead of sleeping blind.
            started = time.monotonic()
            while time.monotonic() - started < _TRIP_TIMEOUT_SECONDS:
                time.sleep(_TRIP_POLL_SECONDS)
                if _over_temp_tripped(client, unit_id):
                    trip_seconds = time.monotonic() - started
                    break
            if trip_seconds is None:
                raise RuntimeError(
                    f"Over-temperature protection did not trip within "
                    f"{_TRIP_TIMEOUT_SECONDS}s of lowering "
                    f"0x{TEMP_LIMIT_REGISTER:04X}"
                )
            # Production is halted, PV released toward open-circuit.
            mid = _pv_snapshot(client, unit_id)
            time.sleep(off_seconds)
        finally:
            _restore_temp_limit(client, unit_id, original)

        after = _pv_snapshot(client, unit_id)
        _LOGGER.info(
            "Temperature limit restored to %d (tripped after %.1fs, mid: %s, "
            "after: %s); production typically re-engages with a fresh MPPT "
            "sweep within a minute",
            original,
            trip_seconds if trip_seconds is not None else -1.0,
            mid,
            after,
        )
        return {
            "original_limit": original,
            "trip_seconds": trip_seconds,
            "before": before,
            "mid": mid,
            "after": after,
        }
    finally:
        client.close()
