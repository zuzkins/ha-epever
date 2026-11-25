"""Read-only Modbus communication for Epever HP series hybrid inverters.

No public register map exists; what is known comes from dumps of an
HP5542-AH1050P2-A. Reads outside its blocks get no answer at all instead of a
Modbus exception. Nothing here may write to the inverter.
"""

from typing import Any

from pymodbus import FramerType
from pymodbus.client import ModbusTcpClient

from .epever_com import _INIT_SEQUENCE, EpeverReadError, _read_segment

# The live data block. It also answers with FC 0x03, with the same values.
HP_FIRST_REGISTER = 0x3000
HP_REGISTER_COUNT = 200
# Largest read verified on the device.
HP_BLOCK_SIZE = 16


def get_hp_data(host: str, port: int, unit_id: int = 1) -> dict[str, Any]:
    """Read the live data block of an HP inverter.

    Returns:
        {"registers": {address: raw value}}.

    Raises:
        EpeverReadError: if connecting or any block read fails.
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
        return {"registers": registers}
    finally:
        client.close()
