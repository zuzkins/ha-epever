#!/usr/bin/env python3
"""Read-only probe of Epever holding registers that may control charging.

Phase 2 of docs/epever_mppt_reacquire_experiment.md. Candidates:

  - 0x901B power component temperature upper limit (default 8500 =
    85.00 C). Verified by joeyh76 on a Tracer4215BN: writing a low value
    (e.g. 1000) fakes an over-temperature condition and stops power
    production within seconds; restoring the original value re-enables.
  - 0x90BD suspected RAM-backed charge-current control seen in
    PAL-ADP-50AN traffic (symbioquine). Not readable on the Tracer4215BN;
    this probe answers whether it exists on our unit at all.
  - 0x9107 lithium-protection bit flags with 0x9010/0x9011 low-temp
    cutoffs - a possible alternative disable path.

This script performs NO writes. It reads:

  1. Rated data (input 0x3000..) - to compare 0x90BD against the unit's
     rated charging current.
  2. Documented settings block (holding 0x9000-0x900E) - baseline sanity
     check that holding-register reads decode correctly.
  3. Holding registers 0x9010-0x90FF in small chunks - exploration map of
     what exists, annotated at the cells of interest.

The Epever WiFi dongle serves one TCP client at a time. Disable the
zepever integration entry in HA (or expect occasional timeouts here and
one failed poll cycle there) while this runs.

Usage:
    pip install pymodbus
    python3 probe_charging_control.py --host 192.168.x.x [--port 9999] [--unit 1]
"""

from __future__ import annotations

import argparse
import time

from pymodbus import FramerType
from pymodbus.client import ModbusTcpClient

# Magic init sequence required by the Epever WiFi dongle after connect.
INIT_SEQUENCE = bytes.fromhex("20020000")

# The device truncates reads that cross internal block boundaries
# (observed on input registers), so keep every read small.
CHUNK = 8
INTER_READ_DELAY = 0.05


def read_chunk(client, kind, address, count, unit_id, attempts=2):
    """Read registers with one retry; returns list (possibly short) or None."""
    read = (
        client.read_input_registers
        if kind == "input"
        else client.read_holding_registers
    )
    for attempt in range(attempts):
        try:
            result = read(address=address, count=count, device_id=unit_id)
        except Exception as err:  # noqa: BLE001 - keep probing
            print(f"  0x{address:04X} +{count}: exception {err!r}")
            result = None
        else:
            if not result.isError():
                return result.registers
            print(f"  0x{address:04X} +{count}: {result}")
        if attempt + 1 < attempts:
            time.sleep(0.5)
    return None


# Cells of interest (see docs/epever_mppt_reacquire_experiment.md phase 2).
ANNOTATIONS = {
    0x9010: "low-temp charge cutoff (used when 0x9107 bit 0x200 set)",
    0x9011: "low-temp discharge cutoff (used when 0x9107 bit 0x100 set)",
    0x9017: "battery temp warning upper limit",
    0x901B: "power component temp upper limit - THE disable knob, expect 8500",
    0x901C: "power component temp upper limit recover",
    0x9107: "lithium protection bit flags",
    0x90BD: "suspected RAM-backed charge-current control (may not exist)",
}


def dump(kind, start, registers):
    for offset, value in enumerate(registers):
        address = start + offset
        note = ANNOTATIONS.get(address, "")
        print(
            f"  {kind} 0x{address:04X}: {value:6d}  0x{value:04X}  /100={value / 100:8.2f}"
            + (f"  <-- {note}" if note else "")
        )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--host", required=True)
    parser.add_argument("--port", type=int, default=9999)
    parser.add_argument("--unit", type=int, default=1)
    args = parser.parse_args()

    client = ModbusTcpClient(
        host=args.host, port=args.port, retries=1, framer=FramerType.RTU
    )
    if not client.connect():
        raise SystemExit(
            f"Could not connect to {args.host}:{args.port} - is the HA "
            f"integration hogging the dongle's single connection?"
        )
    client.send(INIT_SEQUENCE)

    try:
        print("== Rated data (input 0x3000-0x3008, 0x300E) ==")
        print("   0x3005 = rated charging current x100 - compare with 0x90BD")
        registers = read_chunk(client, "input", 0x3000, 9, args.unit)
        if registers:
            dump("IR", 0x3000, registers)
        time.sleep(INTER_READ_DELAY)
        registers = read_chunk(client, "input", 0x300E, 1, args.unit)
        if registers:
            dump("IR", 0x300E, registers)

        print("\n== Documented settings (holding 0x9000-0x900E) ==")
        time.sleep(INTER_READ_DELAY)
        registers = read_chunk(client, "holding", 0x9000, 15, args.unit)
        if registers:
            dump("HR", 0x9000, registers)

        print("\n== Exploration scan (holding 0x9010-0x90FF) ==")
        for start in range(0x9010, 0x9100, CHUNK):
            time.sleep(INTER_READ_DELAY)
            registers = read_chunk(client, "holding", start, CHUNK, args.unit)
            if registers:
                dump("HR", start, registers)

        # 0x9100-0x9105 hold the device passwords in plaintext ASCII -
        # deliberately skipped. 0x9106 is comm config, 0x9107 the lithium
        # protection flags.
        print("\n== Comm config + lithium flags (holding 0x9106-0x9109) ==")
        time.sleep(INTER_READ_DELAY)
        registers = read_chunk(client, "holding", 0x9106, 4, args.unit)
        if registers:
            dump("HR", 0x9106, registers)

        print("\nDone. Cells to look at:")
        print("  HR 0x901B - should read ~8500 (85.00 C); the verified disable")
        print("    knob (write 1000 to fake over-temp, restore to re-enable).")
        print("  HR 0x90BD - if it reads at all, the RAM-backed charge-current")
        print("    hypothesis is testable on this unit; compare /100 with the")
        print("    rated charging current (IR 0x3005).")
    finally:
        client.close()


if __name__ == "__main__":
    main()
