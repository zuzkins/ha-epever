#!/usr/bin/env python3
"""Read-only probe 2: does an Epever inverter keep its data in holding registers?

Needs only Python 3.5+ (no packages). Sends Modbus RTU over TCP reads
(FC 0x01, 0x02, 0x03, 0x04, 0x11, 0x2B) and never writes. Disable the Home Assistant integration
and close other apps first: the WiFi adapter accepts a single TCP client.

    python3 probe_holding.py 192.168.10.19
"""

import argparse
import socket
import struct
import sys
import time

# Wakes up the WiFi adapter; same sequence as the integration sends.
INIT_SEQUENCE = bytes.fromhex("20020000")

READ_FUNCTIONS = (3, 4)
# Answered by the HP5542 in the first probe; proves the link is still alive.
CANARY = (3, 0x9000)

# Read with both functions, so function and address are not mixed up. Labels
# are what the public maps say there: T = Tracer, U = UPower (2019 document),
# H = UPower-Hi/UP5000. They are hypotheses for this inverter.
COMPARE = (
    (0x3000, "T rated PV V"),
    (0x3100, "T PV V"),
    (0x3200, "T battery status"),
    (0x3400, "H nominal grid V"),
    (0x3416, "H nominal PV V"),
    (0x3500, "U/H grid V"),
    (0x3519, "U PV V"),
    (0x3521, "H output V"),
    (0x3533, "U output V / H heat sink"),
    (0x3549, "H PV V"),
    (0x354C, "U battery V / H PV W high"),
    (0x3580, "H battery V"),
    (0x3586, "H battery SOC"),
    (0x9000, "T battery type"),
    (0x9600, "U/H backlight s x100"),
    (0x9602, "U/H temperature unit, 0-1"),
    (0x9607, "U battery type / H charging mode"),
    (0x9608, "U battery Ah / H output priority"),
    (0x960F, "U boost recovery V / H battery type"),
    (0x9610, "H battery Ah"),
    (0x9631, "H output voltage class x100"),
    (0x9632, "H output frequency x100"),
)

# Other read-only requests that can identify the device (complete PDUs).
IDENTIFY = (
    (bytes.fromhex("2b0e0100"), "device identification"),
    (bytes.fromhex("11"), "report server ID"),
    (bytes.fromhex("0221000002"), "discrete 0x2100 x2: U grid bypass, night"),
    (bytes.fromhex("0220000001"), "discrete 0x2000: T over temperature"),
    (bytes.fromhex("0101060001"), "coil 0x0106 (read): U output switch"),
)

SCAN_RANGES = ((0x3000, 0x3600), (0x9000, 0x9100), (0x9600, 0x9650))
BLOCK = 16


def crc16(data):
    """Return the Modbus CRC in wire order."""
    crc = 0xFFFF
    for byte in data:
        crc ^= byte
        for _ in range(8):
            crc = (crc >> 1) ^ 0xA001 if crc & 1 else crc >> 1
    return struct.pack("<H", crc)


def parse(raw, unit, function, count):
    """Find a CRC-valid reply of the requested size (or exception), else None.

    Requiring the size keeps a late reply to a different read from being
    taken for this one.
    """
    for start in range(len(raw)):
        frame = raw[start:]
        if len(frame) < 5 or frame[0] != unit:
            continue
        if frame[1] == function | 0x80 and crc16(frame[:3]) == frame[3:5]:
            return ("exception", frame[2])
        end = 3 + 2 * count
        if frame[1] == function and frame[2] == 2 * count:
            if crc16(frame[:end]) == frame[end : end + 2]:
                return ("values", struct.unpack(">%dH" % count, frame[3:end]))
    return None


class Link:
    """One TCP connection to the adapter, reopened when it drops."""

    def __init__(self, host, port, unit, timeout):
        self.host = host
        self.port = port
        self.unit = unit
        self.timeout = timeout
        self.sock = None
        self.known = set()  # (function, address) that answered on its own

    def close(self):
        if self.sock:
            self.sock.close()
            self.sock = None

    def _open(self):
        self.sock = socket.create_connection((self.host, self.port), 5)
        self.sock.sendall(INIT_SEQUENCE)
        time.sleep(0.5)

    def _drain(self):
        self.sock.settimeout(0.1)
        try:
            while True:
                if not self.sock.recv(512):
                    raise ConnectionError("adapter closed the connection")
        except socket.timeout:
            pass

    def read(self, function, address, count):
        """Return (kind, payload, seconds)."""
        if function not in READ_FUNCTIONS:
            raise ValueError("only reads are allowed")
        raw = b""
        started = time.monotonic()
        try:
            if self.sock is None:
                self._open()
            self._drain()
            request = struct.pack(">BBHH", self.unit, function, address, count)
            self.sock.sendall(request + crc16(request))
            started = time.monotonic()
            while True:
                left = started + self.timeout - time.monotonic()
                if left <= 0:
                    break
                self.sock.settimeout(left)
                try:
                    chunk = self.sock.recv(512)
                except socket.timeout:
                    break
                if not chunk:
                    raise ConnectionError("adapter closed the connection")
                raw += chunk
                reply = parse(raw, self.unit, function, count)
                if reply:
                    return reply + (time.monotonic() - started,)
        except OSError as err:
            self.close()
            time.sleep(1)
            return ("error", str(err), 0)
        kind = "unrecognised" if raw else "silent"
        return (kind, raw.hex(), time.monotonic() - started)

    def raw_request(self, pdu):
        """Send one of the IDENTIFY requests; return whatever comes back."""
        if pdu not in [request for request, _ in IDENTIFY]:
            raise ValueError("only the listed reads are allowed")
        raw = b""
        try:
            if self.sock is None:
                self._open()
            self._drain()
            request = bytes([self.unit]) + pdu
            self.sock.sendall(request + crc16(request))
            self.sock.settimeout(self.timeout)
            while True:
                chunk = self.sock.recv(512)
                if not chunk:
                    self.close()
                    break
                raw += chunk
                self.sock.settimeout(0.5)
        except socket.timeout:
            pass
        except OSError as err:
            self.close()
            return "ERROR: %s" % err
        if not raw:
            return "no answer"
        checked = "CRC ok" if crc16(raw[:-2]) == raw[-2:] else "CRC BAD"
        text = "".join(chr(b) if 32 <= b < 127 else "." for b in raw)
        return "%s (%s) %s" % (raw.hex(), checked, text)

    def alive(self):
        """Check the register known to answer, reconnecting if needed."""
        for _ in range(3):
            if self.read(CANARY[0], CANARY[1], 1)[0] == "values":
                return True
            self.close()
            time.sleep(1)
        return False


def describe(kind, payload):
    """Format one result for printing."""
    if kind == "values":
        return "OK " + " ".join("%d" % v for v in payload)
    if kind == "exception":
        return "EXCEPTION code %d" % payload
    if kind == "silent":
        return "no answer"
    return "%s: %s" % (kind.upper(), payload)


def compare(link):
    """Read the same addresses with FC03 and FC04; return functions that answer."""
    print("\n=== 1. same addresses, both functions ===")
    answering = set()
    slowest = 0.0
    for address, label in COMPARE:
        for function in READ_FUNCTIONS:
            for _ in range(2):  # a single lost frame must not decide this
                kind, payload, seconds = link.read(function, address, 1)
                if kind in ("values", "exception"):
                    break
            if kind == "values":
                answering.add(function)
                link.known.add((function, address))
            if kind in ("values", "exception"):
                slowest = max(slowest, seconds)
            print(
                "  FC%02d 0x%04X  %-36s %-18s %.2fs"
                % (function, address, label, describe(kind, payload), seconds),
                flush=True,
            )
    return answering, slowest


def identify(link):
    """Try the identification requests."""
    print("\n=== 2. identification ===")
    for pdu, label in IDENTIFY:
        print("  %-42s %s" % (label, link.raw_request(pdu)), flush=True)


def scan_block(link, function, address, count, found):
    """Read a block, halving it only where something answers."""
    kind, payload, _ = link.read(function, address, count)
    if kind == "values":
        found[0] += count
        print("  0x%04X: %s" % (address, " ".join("%d" % v for v in payload)), flush=True)
        return
    if kind not in ("silent", "exception"):
        print("  0x%04X x%d %s" % (address, count, describe(kind, payload)), flush=True)
    if count == 1:
        return
    if count == BLOCK:
        # Sample a few single registers before paying for a full bisection.
        samples = [link.read(function, address + o, 1) for o in (0, 5, 10, 15)]
        known = any(
            f == function and address <= a < address + count for f, a in link.known
        )
        if not known and not any(s[0] == "values" for s in samples):
            return
    half = count // 2
    scan_block(link, function, address, half, found)
    scan_block(link, function, address + half, count - half, found)


def scan(link, function):
    """Dump every answering register in the scan ranges; False if link died."""
    for first, end in SCAN_RANGES:
        print("\n=== 3. FC%02d scan 0x%04X-0x%04X ===" % (function, first, end - 1))
        found = [0]
        for address in range(first, end, BLOCK):
            before = found[0]
            scan_block(link, function, address, BLOCK, found)
            if found[0] == before and not link.alive():
                print("  link stopped answering at 0x%04X, giving up" % address)
                return False
        print("  (%d registers answered)" % found[0], flush=True)
    return True


def main():
    """Compare functions, then dump with those that answer."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("host")
    parser.add_argument("--port", type=int, default=9999)
    parser.add_argument("--unit", type=int, default=1)
    parser.add_argument("--timeout", type=float, default=3.0)
    parser.add_argument("--scan-timeout", type=float, default=1.0)
    args = parser.parse_args()

    link = Link(args.host, args.port, args.unit, args.timeout)
    try:
        if not link.alive():
            print("The inverter does not answer FC03 0x9000 (unit %d)." % args.unit)
            return 1
        answering, slowest = compare(link)
        identify(link)
        if not link.alive():
            print("  link stopped answering after identification")
            return 1
        link.timeout = max(args.scan_timeout, 4 * slowest)
        print("  slowest reply %.2fs, scan timeout %.2fs" % (slowest, link.timeout))
        for function in sorted(answering):
            if not scan(link, function):
                return 1
        print("\n=== done ===")
        return 0
    finally:
        link.close()


if __name__ == "__main__":
    sys.exit(main())
