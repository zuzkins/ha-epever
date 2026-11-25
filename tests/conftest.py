"""Fixtures: a fake Epever WiFi dongle speaking Modbus RTU over TCP.

Run with: pytest -p no:cacheprovider -o asyncio_mode=auto tests
(needs pytest-homeassistant-custom-component and pymodbus)
"""

import socket
import struct
import threading

import pytest

# 0x3000-0x30C7 of an HP5542-AH1050P2-A at night, from issue #9.
HP_DUMP = [
    0,
    8266,
    50372,
    8728,
    76,
    0,
    0,
    0,
    0,
    0,
    0,
    9984,
    1,
    0,
    128,
    2338,
    33,
    499,
    817,
    2335,
    0,
    1,
    35,
    0,
    0,
    499,
    818,
    757,
    65535,
    23,
    97,
    0,
    3742,
    504,
    65532,
    96,
    65516,
    0,
    0,
    0,
    0,
    0,
    0,
    0,
    0,
    0,
    1000,
    2500,
    250,
    234,
    238,
    252,
    0,
    0,
    1,
    14182,
    22314,
    164,
    72,
    0,
    0,
    0,
    0,
    0,
    0,
    0,
    0,
    0,
    0,
    0,
    0,
    0,
    0,
    0,
    0,
    0,
    0,
    0,
    0,
    0,
    0,
    0,
    72,
    0,
    0,
    0,
    0,
    1,
    0,
    1,
    1,
    0,
    1,
    65532,
    0,
    0,
    0,
    0,
    0,
    250,
    65532,
    96,
    504,
    4,
    0,
    6,
    0,
    6,
    0,
    6,
    0,
    0,
    0,
    0,
    0,
    0,
    0,
    0,
    0,
    178,
    0,
    290,
    0,
    290,
    0,
    290,
    0,
    111,
    0,
    244,
    0,
    244,
    0,
    244,
    0,
    80,
    0,
    177,
    0,
    177,
    0,
    177,
    0,
    103,
    0,
    210,
    0,
    210,
    0,
    210,
    0,
    0,
    0,
    0,
    0,
    0,
    0,
    0,
    0,
    0,
    0,
    0,
    0,
    0,
    0,
    0,
    0,
    0,
    0,
    0,
    0,
    0,
    0,
    0,
    0,
    0,
    0,
    0,
    0,
    0,
    0,
    0,
    0,
    0,
    0,
    0,
    0,
    0,
    0,
    0,
    0,
    0,
    0,
    0,
    0,
    0,
    0,
    0,
    0,
    0,
]


def crc16(data):
    """Return the Modbus CRC in wire order."""
    crc = 0xFFFF
    for byte in data:
        crc ^= byte
        for _ in range(8):
            crc = (crc >> 1) ^ 0xA001 if crc & 1 else crc >> 1
    return struct.pack("<H", crc)


class FakeDongle:
    """Serves registers; records every request."""

    def __init__(self, registers, *, silent_outside):
        self.registers = registers
        self.silent_outside = silent_outside
        self.requests = []
        self.sock = socket.socket()
        self.sock.bind(("127.0.0.1", 0))
        self.sock.listen()
        self.port = self.sock.getsockname()[1]
        threading.Thread(target=self._serve, daemon=True).start()

    def _serve(self):
        while True:
            try:
                client, _ = self.sock.accept()
            except OSError:
                return
            with client:
                try:
                    self._handle(client)
                except OSError:
                    pass

    def _handle(self, client):
        while data := client.recv(512):
            data = data.removeprefix(bytes.fromhex("20020000"))
            for start in range(0, len(data) // 8 * 8, 8):
                unit, function, address, count = struct.unpack(
                    ">BBHH", data[start : start + 6]
                )
                self.requests.append((function, address, count))
                wanted = range(address, address + count)
                if function in (3, 4) and all(a in self.registers for a in wanted):
                    values = [self.registers[a] for a in wanted]
                    reply = bytes([unit, function, 2 * count])
                    reply += struct.pack(f">{count}H", *values)
                elif self.silent_outside:
                    continue
                else:
                    reply = bytes([unit, function | 0x80, 2])
                client.sendall(reply + crc16(reply))


@pytest.fixture(autouse=True)
def _custom_integrations(enable_custom_integrations, socket_enabled):
    """Load custom_components and allow the loopback connection."""


@pytest.fixture
def hp_dongle():
    """Dongle of an HP inverter."""
    dongle = FakeDongle(dict(enumerate(HP_DUMP, 0x3000)), silent_outside=True)
    yield dongle
    dongle.sock.close()


@pytest.fixture
def tracer_dongle():
    """Dongle of a Tracer."""
    registers = {a: 1200 + a % 100 for a in range(0x3100, 0x3113)}
    registers |= {0x311A: 80, 0x311B: 2000, 0x3200: 0, 0x3201: 4, 0x3202: 1}
    registers |= {a: 5 for a in range(0x3304, 0x3314)}
    registers |= {0x331D: 2500, 0x331E: 2400, 0x903D: 0}
    dongle = FakeDongle(registers, silent_outside=False)
    yield dongle
    dongle.sock.close()
