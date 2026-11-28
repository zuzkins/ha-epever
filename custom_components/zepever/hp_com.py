"""Read-only Modbus communication for Epever HP series hybrid inverters.

The register meanings come from the HP-AH definitions in EPEVER's Solar
Guardian Android app; the addresses were checked against dumps of an
HP5542-AH1050P2-A. The app also lists registers that reset or reconfigure the
inverter: nothing here may write. Reads of unknown addresses can go
unanswered instead of raising a Modbus exception.
"""

import logging
from collections.abc import Sequence
from typing import Any

from pymodbus import FramerType
from pymodbus.client import ModbusTcpClient

from .epever_com import _INIT_SEQUENCE, EpeverReadError, _read_segment

_LOGGER = logging.getLogger(__name__)

# The live data block. It also answers with FC 0x03, with the same values.
HP_FIRST_REGISTER = 0x3000
HP_REGISTER_COUNT = 200
# Largest read verified on the device.
HP_BLOCK_SIZE = 16

# Energy counters and totals, (address, count), read every few minutes. Split
# so that no read spans undefined addresses. Each is read on its own: any of
# them may go unanswered.
HP_ENERGY_BLOCKS = (
    (0x1000, 16),
    (0x1018, 10),
    (0x102A, 8),
    (0x1046, 16),
)
# Total PV power and its neighbour, outside the live block but read on every
# poll like it.
HP_PV_POWER_BLOCK = (0x1056, 2)

# Fault bits: address -> bit -> name.
HP_FAULTS: dict[int, dict[int, str]] = {
    0x3006: {
        0: "DC bus overvoltage",
        2: "Inverter output overcurrent",
        4: "Battery overvoltage",
        5: "Battery undervoltage",
        6: "DC bus undervoltage",
        7: "Inverter output overvoltage",
        8: "Utility overvoltage",
        9: "Utility overcurrent",
        10: "Inverter over temperature",
        11: "Battery over temperature",
        12: "Ambient over temperature",
        13: "PV module 1 over temperature",
        14: "PV module 2 over temperature",
        15: "PV1 overvoltage",
    },
    0x3007: {
        0: "PV1 undervoltage",
        1: "PV1 overcurrent",
        2: "PV2 overvoltage",
        3: "PV2 undervoltage",
        4: "PV2 overcurrent",
        5: "Battery or bus hardware overvoltage",
        6: "Inverter hardware overvoltage",
        7: "Inverter hardware overcurrent",
        8: "DC bus hardware overcurrent",
        9: "Utility undervoltage",
        12: "Utility pre-charge timeout",
        13: "Utility relay adhesion",
        14: "PV module hardware fault",
        15: "Utility frequency error",
    },
    0x3008: {
        0: "Inverter voltage offset error",
        1: "Load current offset error",
        3: "Inverter current offset error",
        4: "DC bus current offset error",
        5: "Battery overcurrent",
        6: "Boost drive error",
        7: "Battery disconnected",
        8: "Auxiliary power supply error",
    },
    0x3009: {
        0: "Load overload",
        1: "Inverter undervoltage",
        2: "Battery undervoltage alarm",
        3: "Load wiring error",
        4: "PV1 pre-charge timeout",
        5: "PV2 pre-charge timeout",
        6: "EEPROM error",
        7: "Load overload lock",
        8: "Battery activation failed",
        12: "Booster module over temperature",
        14: "AFCI arc detected",
    },
}

# Conditions that are normal on some installations, so not faults.
HP_NOTICES: dict[int, dict[int, str]] = {
    0x3008: {
        9: "Remote temperature sensor not connected",
        10: "Ambient temperature sensor not connected",
        11: "PV1 temperature sensor not connected",
        12: "PV2 temperature sensor not connected",
        13: "Inverter temperature sensor not connected",
        14: "Low temperature: charging stopped",
        15: "Low temperature: discharging stopped",
    },
    0x3009: {13: "AFCI not connected"},
}


def active_bits(
    registers: dict[int, int], definitions: dict[int, dict[int, str]]
) -> list[str]:
    """Return the names of the defined bits that are set."""
    return [
        name
        for address, bits in definitions.items()
        for bit, name in bits.items()
        if registers[address] >> bit & 1
    ]


def get_hp_data(
    host: str,
    port: int,
    unit_id: int = 1,
    energy_blocks: Sequence[tuple[int, int]] = (),
) -> dict[str, Any]:
    """Read the live data block, and optionally blocks outside it.

    Returns:
        {"registers": {address: raw value}, "energy": ..., "energy_errors": ...}.
        "energy" has the same shape as "registers" and holds the blocks that
        were read; "energy_errors" maps the first address of a failed block to
        its error. After a failure the remaining blocks are not read, and
        appear in neither.

    Raises:
        EpeverReadError: if connecting or any live block read fails. Energy
            failures don't raise.
    """
    client = ModbusTcpClient(host=host, port=port, retries=1, framer=FramerType.RTU)
    try:
        if not client.connect():
            raise EpeverReadError(
                "connect", None, ConnectionError(f"could not connect to {host}:{port}")
            )
        client.send(_INIT_SEQUENCE)

        registers: dict[int, int] = {}
        end = HP_FIRST_REGISTER + HP_REGISTER_COUNT
        for address in range(HP_FIRST_REGISTER, end, HP_BLOCK_SIZE):
            count = min(HP_BLOCK_SIZE, end - address)
            values = _read_segment(client, "hp_live", address, count, unit_id)
            if values is None:
                # A Tracer may answer these reads with an error; accepting
                # that would set up a device without data.
                raise EpeverReadError(
                    "hp_live", address, ValueError("error or short response")
                )
            registers.update(enumerate(values, address))

        energy: dict[int, int] = {}
        energy_errors: dict[int, str] = {}
        # After the live block, and stopping at the first failure, because a
        # timed-out RTU stream can't be trusted afterwards.
        for address, count in energy_blocks:
            try:
                values = _read_segment(client, "hp_energy", address, count, unit_id)
            except EpeverReadError as err:
                energy_errors[address] = str(err)
                _LOGGER.debug("Energy block not readable: %s", err)
                break
            if values is None:
                energy_errors[address] = "error or short response"
                break
            energy.update(enumerate(values, address))
        return {
            "registers": registers,
            "energy": energy,
            "energy_errors": energy_errors,
        }
    finally:
        client.close()
