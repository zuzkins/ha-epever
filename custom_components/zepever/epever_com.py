"""Simple Modbus communication for Epever devices."""

from typing import Any

from pymodbus import FramerType
from pymodbus.client import ModbusTcpClient


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
        client.send(bytes.fromhex("20020000"))

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
        client.send(bytes.fromhex("20020000"))

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

        return data

    except (ConnectionError, TimeoutError, ValueError, IndexError):
        return None
    finally:
        client.close()
