#!/usr/bin/env python3
"""Read-only probe: find out which registers an Epever device answers.

Needs only Python 3.8+ (no packages). Sends Modbus RTU over TCP reads
(FC 0x03 and 0x04) and never writes. Disable the Home Assistant integration
and close other apps first: the WiFi adapter accepts a single TCP client.

    python3 probe_registers.py 192.168.10.19
"""

import argparse
import socket
import struct
import time

# Wakes up the WiFi adapter; same sequence as the integration sends.
INIT_SEQUENCE = bytes.fromhex("20020000")

READS = (
    # function, address, count, label
    (4, 0x3100, 1, "Tracer PV voltage"),
    (4, 0x3100, 19, "Tracer realtime block, as the integration reads it"),
    (4, 0x3200, 3, "Tracer status"),
    (3, 0x9000, 1, "Tracer battery type"),
    (4, 0x3500, 1, "UPower-Hi grid voltage"),
    (4, 0x3521, 1, "UPower-Hi load voltage"),
    (4, 0x3549, 1, "UPower-Hi PV voltage"),
    (4, 0x3580, 1, "UPower-Hi battery voltage"),
    (3, 0x9607, 1, "UPower-Hi charging mode"),
)


def crc16(data):
    """Return the Modbus CRC in wire order."""
    crc = 0xFFFF
    for byte in data:
        crc ^= byte
        for _ in range(8):
            crc = (crc >> 1) ^ 0xA001 if crc & 1 else crc >> 1
    return struct.pack("<H", crc)


def parse(raw, unit, function):
    """Find a CRC-valid reply to this request in the raw bytes, else None."""
    for start in range(len(raw)):
        frame = raw[start:]
        if len(frame) < 5 or frame[0] != unit:
            continue
        if frame[1] == function | 0x80 and crc16(frame[:3]) == frame[3:5]:
            return ("exception", frame[2])
        if frame[1] == function:
            size = frame[2]
            end = 3 + size
            if size % 2 == 0 and crc16(frame[:end]) == frame[end : end + 2]:
                return ("values", struct.unpack(">%dH" % (size // 2), frame[3:end]))
    return None


def drain(sock):
    """Throw away unsolicited or late bytes and return them."""
    stale = b""
    sock.settimeout(0.2)
    try:
        while True:
            chunk = sock.recv(512)
            if not chunk:
                raise ConnectionError("adapter closed the connection")
            stale += chunk
    except socket.timeout:
        return stale


def query(sock, unit, function, address, count, timeout):
    """Send one read; return (parsed reply or None, raw bytes)."""
    request = struct.pack(">BBHH", unit, function, address, count)
    sock.sendall(request + crc16(request))
    raw = b""
    deadline = time.monotonic() + timeout
    while True:
        left = deadline - time.monotonic()
        if left <= 0:
            return None, raw
        sock.settimeout(left)
        try:
            chunk = sock.recv(512)
        except socket.timeout:
            return None, raw
        if not chunk:
            raise ConnectionError("adapter closed the connection, got: " + raw.hex())
        raw += chunk
        reply = parse(raw, unit, function)
        if reply:
            return reply, raw


def probe(args, unit, init):
    """Run all reads for one unit ID; return counts per outcome."""
    print("\n=== unit %d, init sequence %s ===" % (unit, "sent" if init else "NOT sent"))
    counts = {"values": 0, "exception": 0, "garbled": 0, "silent": 0, "error": 0}
    sock = None
    for function, address, count, label in READS:
        name = "FC%02d 0x%04X x%-2d" % (function, address, count)
        try:
            if sock is None:
                sock = socket.create_connection((args.host, args.port), args.timeout)
                if init:
                    sock.sendall(INIT_SEQUENCE)
                    time.sleep(0.5)
            stale = drain(sock)
            if stale:
                print("  (unsolicited bytes: %s)" % stale.hex())
            reply, raw = query(sock, unit, function, address, count, args.timeout)
        except OSError as err:
            counts["error"] += 1
            outcome = "CONNECTION ERROR: %s" % err
            if sock:
                sock.close()
            sock = None
            time.sleep(1)
        else:
            if reply and reply[0] == "values":
                counts["values"] += 1
                outcome = "OK %s" % list(reply[1])
                if len(reply[1]) != count:
                    outcome += " (asked for %d)" % count
            elif reply:
                counts["exception"] += 1
                outcome = "EXCEPTION code %d" % reply[1]
            elif raw:
                counts["garbled"] += 1
                outcome = "UNRECOGNISED bytes: %s" % raw.hex()
            else:
                counts["silent"] += 1
                outcome = "no answer"
        print("  %s %-52s %s" % (name, label, outcome), flush=True)
    if sock:
        sock.close()
    time.sleep(1)  # let the adapter free its only client slot
    return counts


def main():
    """Probe each unit ID and summarise."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("host")
    parser.add_argument("--port", type=int, default=9999)
    parser.add_argument("--units", type=int, nargs="+", default=[1, 4, 10])
    parser.add_argument("--timeout", type=float, default=3.0)
    args = parser.parse_args()

    runs = [(unit, True) for unit in args.units] + [(args.units[0], False)]
    results = [(unit, init, probe(args, unit, init)) for unit, init in runs]

    print("\n=== summary ===")
    for unit, init, counts in results:
        print("unit %-3d init=%-5s %s" % (unit, init, counts))


if __name__ == "__main__":
    main()
