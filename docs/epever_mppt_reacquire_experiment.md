# EPEVER Tracer AN MPPT Reacquire Experiment

## Goal

Test whether the EPEVER Tracer AN can be forced to perform a fresh MPPT reacquire/sweep by briefly disabling and re-enabling the charging function over Modbus.

The suspected control point is:

```text
Modbus coil address: 0
Meaning: charging device on/off
false / 0 = charging disabled
true  / 1 = charging enabled
```

This is **not** a documented “force MPPT sweep” command. The experiment checks whether toggling the charger causes the controller firmware to reacquire the MPP after charging is re-enabled.

## Safety notes

- Do not disconnect the battery from the controller during the test.
- Do not write random holding registers.
- Do not change battery voltage/current/charging parameters for this experiment.
- Do not run the toggle repeatedly in a tight loop.
- Start with a manual single test.
- Use a conservative off-time, for example 3–5 seconds.
- Rate-limit any automation later, for example no more than once every 5–10 minutes.

The Wi-Fi adapter should remain online as long as the controller remains powered from the battery. This test disables charging, not the whole controller.

## What to observe

Log or watch these values before, during, and after the toggle:

```text
PV voltage
PV current
PV power
Battery voltage
Battery current / charging current
Charging equipment status
```

Useful EPEVER Modbus input registers commonly used for this:

```text
0x3100  PV voltage
0x3101  PV current
0x3102  PV power low word
0x3103  PV power high word
0x3201  charging equipment status
```

A successful reacquire would look roughly like:

```text
1. Charging is disabled.
2. PV current/power drops close to zero.
3. PV voltage may rise toward open-circuit voltage.
4. Charging is re-enabled.
5. Controller settles at a new PV voltage/current operating point.
6. PV power is better than before if it was previously stuck after cloud movement.
```

An unsuccessful result would look like:

```text
1. Charging is disabled.
2. Charging is re-enabled.
3. Controller returns to the same bad operating point.
4. No meaningful MPPT reacquire behavior is observed.
```

## Home Assistant manual service call

First try this manually from Developer Tools → Services / Actions.

Replace `epever` with the actual Modbus hub name from your Home Assistant configuration.

### Turn charging off

```yaml
action: modbus.write_coil
data:
  hub: epever
  slave: 1
  address: 0
  state: false
```

Wait 3–5 seconds.

### Turn charging back on

```yaml
action: modbus.write_coil
data:
  hub: epever
  slave: 1
  address: 0
  state: true
```

## Home Assistant script

Example script:

```yaml
alias: EPEVER force MPPT reacquire
sequence:
  - action: modbus.write_coil
    data:
      hub: epever
      slave: 1
      address: 0
      state: false

  - delay:
      seconds: 5

  - action: modbus.write_coil
    data:
      hub: epever
      slave: 1
      address: 0
      state: true
mode: single
```

## Suggested guarded automation logic

Do not automate immediately. After manual testing proves that the toggle is useful, add conditions such as:

- PV power is unexpectedly low compared with available irradiance.
- PV voltage appears stuck at an obviously poor value.
- Battery is not full.
- Charging is allowed.
- The controller is not in equalize/boost/float behavior where interruption would be undesirable.
- The toggle has not run recently.

Example conceptual logic:

```text
IF battery is not full
AND PV should be producing
AND PV power is suspiciously low
AND last_reacquire_trigger was more than 10 minutes ago
THEN toggle charging off for 5 seconds and back on
```

## Python direct Modbus TCP test

Use this only if the Wi-Fi adapter exposes Modbus TCP directly.

Update the host, port, and device ID.

```python
from time import sleep
from pymodbus.client import ModbusTcpClient

HOST = "192.168.x.x"
PORT = 9999
DEVICE_ID = 1
OFF_SECONDS = 5

client = ModbusTcpClient(HOST, port=PORT, timeout=5)

try:
    if not client.connect():
        raise RuntimeError("Could not connect to EPEVER Modbus TCP endpoint")

    print("Disabling charging...")
    result = client.write_coil(0, False, device_id=DEVICE_ID)
    print(result)

    sleep(OFF_SECONDS)

    print("Enabling charging...")
    result = client.write_coil(0, True, device_id=DEVICE_ID)
    print(result)

finally:
    client.close()
```

If the adapter uses RTU-over-TCP rather than true Modbus TCP, this Python client may need a different framer/client setup.

## Possible custom Home Assistant integration service

If using a custom integration, expose a service such as:

```yaml
service: epever.force_mppt_reacquire
fields:
  device_id:
    required: true
  off_seconds:
    default: 5
```

Implementation behavior:

```text
1. Validate off_seconds, for example min 2, max 15.
2. Write coil 0 false.
3. Wait off_seconds.
4. Write coil 0 true.
5. Log before/after values if available.
6. Refuse or warn if called too frequently.
```

Pseudo-code:

```python
async def force_mppt_reacquire(device, off_seconds: int = 5):
    off_seconds = max(2, min(off_seconds, 15))

    await device.write_coil(address=0, value=False)
    await asyncio.sleep(off_seconds)
    await device.write_coil(address=0, value=True)
```

## Result checklist

Record these during the test:

```text
Date/time:
Weather/cloud condition:
Battery SOC / voltage:
PV voltage before:
PV current before:
PV power before:
Charging status before:

Charging disabled at:
PV voltage while disabled:
PV current while disabled:
PV power while disabled:

Charging re-enabled at:
PV voltage after 10 s:
PV current after 10 s:
PV power after 10 s:
Charging status after 10 s:

PV voltage after 60 s:
PV current after 60 s:
PV power after 60 s:
Charging status after 60 s:

Did it find a better operating point? yes/no
Did Wi-Fi stay connected? yes/no
Any errors/alarms? yes/no
```

## Expected next decision

If the experiment works:

- Add a Home Assistant button/service named `Force MPPT reacquire`.
- Add a cooldown helper.
- Add automation only after collecting enough behavior data.

If the experiment does not work:

- The documented charging on/off coil is not enough to force a new sweep.
- Further options would require undocumented commands, vendor firmware behavior, or hardware-side PV interruption tests.
- Firmware modification would be high risk and should not be the first approach.

## Result — 2026-07-03: coil 0 is a no-op on the Tracer AN

Tested via the `zepever` integration (button + `zepever.force_mppt_reacquire`
service, coil toggle over RTU-over-TCP through the WiFi dongle, 5 s
off-window):

```text
before: PV 23.39 V / 1.14 A / 26.75 W
after:  PV 23.41 V / 1.20 A / 28.10 W   (~40 ms after re-enable)
```

- Both coil writes were acknowledged (`WriteSingleCoilResponse` echo).
- Charging never stopped and PV voltage never rose toward open-circuit.
- The ACK is meaningless: a Modbus Write Single Coil response is just an
  echo of the request. The Tracer AN echoes writes to coils it does not
  implement.

**Why:** coil 0 "charging device on/off" does not exist in the Tracer AN /
B-series protocol. It comes from a different Epever protocol family
(LS-B/ViewStar). The B-series coil map only has load-side controls:

```text
0x0002  manual load control
0x0003  default load control
0x0005  load test mode
0x0006  force load on/off
```

Sources:

- <https://github.com/kasbert/epsolar-tracer/blob/master/pyepsolartracer/registers.py>
- <https://devices.esphome.io/devices/epever_mptt_tracer_an/>

The integration's button/service from this phase is left in place but is a
confirmed no-op on this hardware.

## Phase 2: disable charging via holding registers

Findings from the scraped forum threads (2026-07-03; thread PDFs reviewed,
posts referenced by number):

### Primary candidate: 0x901B fake over-temperature — verified by others

From "EPever MPPT external enable/disable" post #17 (joeyh76, 2025-10-30),
confirmed working on a Tracer4215BN:

```text
Disable:  write HR 0x901B = 1000   (power component temp upper limit,
                                    10.00 °C — instantly "over temp")
          → controller stops producing power within a few seconds
Re-enable: write HR 0x901B = 8500  (restore original, 85.00 °C)
```

`0x901B` is the *documented* "power component temperature upper limit"
(×100). `0x901C` is the matching recover threshold — after restoring
`0x901B`, production resumes because the actual component temperature is
back under the limit. One write per direction.

Observability during the test: discrete input `0x2000` ("over temperature
inside the device", mirrored at input `0x3170`) should flip on while
disabled; the charging-status register `0x3201` should leave the RUNNING
state.

### Secondary candidate: 0x90BD (may not exist on this unit)

Same thread, post #18 (symbioquine): values written to `0x90BD` make
*larger* Tracer units shut down charging temporarily — observed in
PAL-ADP-50AN parallel-adapter traffic. Suspected **RAM-backed** (no flash
wear), which would make it the better long-term knob — but safe values are
unknown, and post #19 (joeyh76): `0x90BD` is **not readable on a
Tracer4215BN**. The read-only probe answers whether it exists here at all.
Observed `8000` on a Tracer8420AN (80 A unit), suggesting max charging
current × 100.

### Also learned

- Coil `0x0` "Charging device on/off" appears only in the
  EpeverBSeriesControllerProtocolV2.3 PDF and not in 1733_modbus_protocol —
  documented for the family, unimplemented on AN/BN hardware. Consistent
  with the phase-1 negative result.
- `0x9107` holds lithium-protection bit flags
  (`0x100` low-temp discharge, `0x200` low-temp charge, `0x400` protection
  disabled, `0x800` high-temp reduced charging — the last one not honored
  on Tracer AN V1.55/V2.00/V2.02), with cutoff temperatures in
  `0x9010`/`0x9011`. A possible alternative disable path, but our unit
  reports the hard-coded 25.00 °C battery-temp sentinel, so temperature
  would be "fake real" — not pursued for now.
- Temperature *window* tricks (making 25 °C fall outside the allowed
  charging range) are constrained by firmware value validation and
  probably can't work (post #16).
- Registers `0x9100-0x9105` hold both device passwords in plaintext ASCII,
  readable and writable without login. Undocumented commands `0x41`
  (login), `0x42` (modify device info), `0x43` (read discontinuous
  registers) exist. Not needed for this experiment.
- Settings registers are validated and some must be written as a whole
  block (e.g. RTC); single-register writes to `0x901B` are fine per the
  verified report.

Sources (forum threads block scrapers; fetch manually):

- <https://diysolarforum.com/threads/epever-mppt-external-enable-disable.22198/>
  — 0x901B method (#17), 0x90BD notes (#18, #19)
- <https://diysolarforum.com/threads/epever-tracer-modbus-digging-deeper.108305/>
  — register maps, 0x9107 flags, undocumented commands
- <https://gist.github.com/symbioquine/95ba2abaf046c8e034b41e4cf3c334a9>
- <https://wiki.recessim.com/view/EPEVER_SCCs>

### Step 1: read-only probe (safe)

`scripts/probe_charging_control.py` reads the rated-current input register
(`0x3005`), the documented settings block (`0x9000-0x900E`), scans holding
`0x9010-0x90FF` (annotated at the cells of interest), and reads
`0x9106-0x9109`. It skips the password block. No writes.

```bash
pip install pymodbus
python3 scripts/probe_charging_control.py --host 192.168.x.x
```

Disable the zepever integration entry while it runs (the dongle serves one
TCP client), or tolerate occasional timeouts.

Checks:

- `HR 0x901B` reads ≈ `8500` → the fake-over-temp method is applicable
  as-is; note the exact value (it is the restore target) and `0x901C`.
- `HR 0x90BD` readable? If yes, compare `/100` against rated charging
  current (`IR 0x3005`).

### Probe results — 2026-07-03 (test device, 192.168.67.127)

```text
IR 0x3005 = 2000   rated charging current 20.00 A (24 V unit, 520 W → Tracer 20A AN class)
HR 0x901B = 8500   power component temp upper limit 85.00 °C — default, method applicable
HR 0x901C = 7500   recover threshold 75.00 °C
HR 0x9019 = 8500   controller inner temp upper limit
HR 0x901A = 6500   controller inner temp recover
HR 0x9018 = 61736  (signed: -38.00 °C)
HR 0x90BD          NOT readable (IllegalDataAddress) — register absent on this unit
HR 0x9106-0x9109   NOT readable — no lithium-protection flags here
HR 0x9010-0x9017   NOT readable
HR 0x9090-0x9097   readable, meaning unknown (34, 0, 2, 0, 2209, 35, 0, 2500)
```

Conclusions:

- The **0x901B fake-over-temp method is applicable as-is**; restore target
  confirmed `8500`.
- **0x90BD does not exist on this unit** (same as the Tracer4215BN), so the
  RAM-backed option is off the table — every toggle costs 2 settings
  writes, which stays a concern for automation, not for manual tests.
- The lithium-flag alternative path is also absent.

### Supervised write tests — 2026-07-03: 0x901B dead, 0x9019 WORKS

Supervised toggles (write `1000`, live observation every 2 s, guaranteed
restore) on the test device, steady ~26-29 W production:

**`0x901B` (power component limit): ignored by AN firmware.** Held at
`1000` for 62 s with the power component at 27.56 °C (register `0x3112`) —
no trip, no `0x2000` flag, no status change, production unaffected.
joeyh76's method works on the BN series only.

**`0x9019` (controller inner temperature upper limit): the knob.**

```text
t= 0s    write 0x9019 = 1000; PV 23.5 V / 1.08 A / 25.5 W, status 0x000B
t=~10s   protection trips: PV current 0, voltage released to Voc
         (23.5 V → 41.6→46.4 V), 0x2000 flag ON, status 0x0001
t=~12s   restore 0x9019 = 8500: flag clears immediately, status back
         to 0x000B, but PV current stays 0 (voltage drifting at Voc)
t=~40-60s controller re-engages and performs a fresh MPPT sweep
```

**And the original hypothesis got its first confirmation:** before the
toggle the controller sat at 23.5 V / ~26 W; after re-engaging it settled
at **35.4 V / 36.7 W** (+40%, and 35.4 V ≈ 0.77 × Voc is a textbook Vmp).
The controller had been stuck at a bad operating point and the forced
reacquire fixed it. (Cloud drift may account for part of the power delta;
the voltage signature is the reliable tell.)

Timing facts that shaped the implementation:

- The protection loop evaluates roughly **every 10 s** — a blind 5 s
  off-window restores the limit before the trip ever happens (this is why
  the first 0x901B-style button test was a silent no-op). The toggle must
  *wait for the trip*, not sleep.
- The `0x2000` "over temperature inside the device" discrete input is a
  crisp, irradiance-independent trip signal.
- Production resumes ~30-60 s *after* restore; a 0 W reading right after
  the toggle is normal.

### Implemented in the integration (0x9019 method)

The HA button/service (`Force MPPT reacquire` / `zepever.force_mppt_reacquire`)
does, in order:

1. Read `0x9019`; abort with nothing written if unreadable.
2. If it reads the disable value `1000` (leftover from a crashed toggle),
   self-heal: use the probe-confirmed factory default `8500` as the
   restore target and continue.
3. If it reads outside 6000–10000, refuse and write nothing.
4. Write `1000`, then **verify by readback** — this firmware ACKs writes it
   ignores, so an ACK alone proves nothing (phase-1 lesson).
5. Poll the `0x2000` flag every 2 s for up to 30 s; if it never trips,
   restore and raise. On trip, take the mid snapshot (production halted,
   PV at Voc) and dwell `off_seconds`.
6. Restore the original value in a `finally` with 5 attempts, reconnect +
   re-init between attempts, each verified by readback. Final failure logs
   the manual recovery instruction (write the original value to `0x9019`).
7. Single connection throughout; 60 s cooldown in the coordinator;
   trip time and before/mid/after snapshots logged at INFO.

Remaining risks, accepted for sporadic manual use:

- The register is flash-backed: a crash between "write low" and "restore"
  leaves the controller convinced it is overheating **across reboots**
  until `0x9019` is restored (the next button press self-heals it, or
  write `8500` manually).
- Flash wear: 2 writes per toggle. Do not automate on a schedule without
  reconsidering this.
- A whole toggle takes ~15-35 s and the coordinator poll queues behind it;
  sensors go briefly stale and then show 0 W for up to a minute while the
  controller re-engages. Expected, not a fault.
