# Krabby-Uno Task 2: Six-Axis Leg Controller

## Overview

This firmware drives a full leg pair (Left & Right) consisting of **6 Motors**.

## Prerequisites

- **Hardware:**
  - Arduino Mega 2560
  - **6x** BTS7960 43A H-Bridge Drivers
  - **12x** Resistors (10kΩ) for Current Sense protection
  - 12V Power Supply
- **Software:**
  - Python 3
  - Libraries: `pip install pyserial` (the interactive menu uses the stdlib `termios`/`select`, so it works headless over SSH — no `keyboard`/`pynput`/X11 needed)
  - Arduino IDE

---

## 1. Hardware Wiring (Rev 3 — Krabby Uno v0.2)

**Polarity Note:**
* **RPWM / R_EN** = Right (Extend/Forward).
* **LPWM / L_EN** = Left (Retract/Reverse).

| Board     | Joint         | PWM (R, L)       | EN    | Potentiometer | Current Sense | HallA  |
| :-------- | :------------ | :--------------- | :---- | :------------ | :------------ | :----- |
| **FL**    | Yaw (LHY)     | D2, D3           | D22   | A0            | A6            | D50    |
|           | Hip (LHL)     | D4, D5           | D24   | A1            | A7            | D51    |
|           | Knee (LKL)    | D6, D7           | D26   | A2            | A8            | D52    |
| **FR**    | Yaw (RHY)     | D8, D9           | D23   | A3            | A9            | A12    |
|           | Hip (RHL)     | D10, D11         | D25   | A4            | A10           | A13    |
|           | Knee (RKL)    | D12, D13         | D27   | A5            | A11           | A14    |

**Note:** Ensure all Enable (EN) pins are connected and driven HIGH when driving, otherwise calibration will get 'lost' as it will not know where joint positions are.

---

## 2. Installation

### 2.1 Serial RX buffer (leader board, 3-board setup)

When using the **leader** board that forwards telemetry from left/right followers, a small serial RX buffer can overflow and drop bytes (corrupt or missing actuators in telemetry, "can't keep up" on the host). The leader needs a **256-byte** RX buffer for Serial1/Serial2 so it can hold a full ~200-byte forwarded line from each follower while it services USB and the actuator update.

The Makefile passes this define on every build, so you usually don't have to do anything. `make compile-firmware` / `make upload-firmware` bake `-DSERIAL_RX_BUFFER_SIZE=256` into the `arduino-cli compile` invocation unconditionally (see `firmware/Makefile` `BUILD_PROPS`), exactly as CI (`.github/workflows/publish-firmware.yml`) does. `firmware/install.py`'s `platform.local.txt` write is now a **belt-and-suspenders backup for IDE builds, not a requirement** — a `make`-built or CI-built binary already has the 256-byte buffer regardless of whether `install.py` ran or which AVR core version is installed. (Note: IDE builds also need the fetched-library symlink from the "Fetched libraries" section below, or they won't find the BMI270 header.) (Some core versions, e.g. 1.8.7, already default the Mega's RX buffer to 256; passing the define guarantees it on every core version and board variant.)

The manual edits below are only needed if you build the sketch **directly from the Arduino IDE** without the `platform.local.txt` override.

**You do not flash the core separately.** The Arduino “core” is just C++ source that is compiled *with* your sketch into a single firmware image. Change the buffer size, then build and upload as usual.

**Arduino IDE**

- **Option A – One-time edit (survives until you update the AVR board package):**  
  Open the core file (path similar to):
  - Windows: `%LOCALAPPDATA%\Arduino15\packages\arduino\hardware\avr\1.8.7\cores\arduino\HardwareSerial.h`
  - macOS: `~/Library/Arduino15/packages/arduino/hardware/avr/1.8.7/cores/arduino/HardwareSerial.h`  
  Find the block that sets `SERIAL_RX_BUFFER_SIZE` (e.g. `#define SERIAL_RX_BUFFER_SIZE 64`) and change **64** to **256**. Save. Then compile and upload your sketch as usual.

- **Option B – Build flag via platform override:**  
  In the same `avr` package folder (e.g. `.../packages/arduino/hardware/avr/1.8.7/`), create or edit `platform.local.txt` and add:
  ```text
  compiler.c.extra_flags=-DSERIAL_RX_BUFFER_SIZE=256
  compiler.cpp.extra_flags=-DSERIAL_RX_BUFFER_SIZE=256
  ```
  so the define is applied when the core and your sketch are compiled. Then build/upload as usual.

**PlatformIO**

In `platformio.ini` for the board that acts as the leader, add:

```ini
build_flags = -DSERIAL_RX_BUFFER_SIZE=256
```

Then build and upload. No core file edit needed.

**Follower-only boards** do not need this change; only the board that runs `forwardFullLines` (the leader on USB) benefits from the larger buffer.

### 2.2 Telemetry format (wire protocol)

Telemetry is sent as **newline-terminated lines** over serial. The Python side parses each line into a **dict of joint id → values** using `JointTelemetry` in `interfaces/joint_telemetry.py`.

- **Line format:** `<ROLE>; <name> <pos> <pot> <current> <enL> <enR> <pwmL> <pwmR> <saf>; <name> ...; ...`
- **Role prefix:** One of `FRONT`, `UNKNOWN`, `LEFT`, `RIGHT` (no semicolon inside the role).
- **Segment format:** Each joint segment is 9 space-separated values: joint name, position (0–1), pot raw, current raw, enable L/R, PWM L/R, safety.
- **Example:** `FRONT; FLHY 0.723 740 694 0 0 0 0 0;FLHL 0.723 740 691 ...`

On the Arduino side, telemetry is built in **telemetry_manager.h** (struct `JointTelemetry`, `appendTo()`). The old standalone `joint_telemetry.h` was removed; all telemetry formatting and collection lives in `telemetry_manager.h` and `actuator_manager.h`.

### 2.3 Pin revisions (`KRABBY_PIN_REV`)

Wiring is selected at **compile time** in **`arduino/board_pins.h`** (`#define KRABBY_PIN_REV`, default **3**). Rev **3** matches **`MOTOR_HEADER_PINOUT.md`**.

| | **Rev 3** (default, Uno v0.2) | **Rev 2** (Uno v0.1) | **Rev 1** (original) |
|---|---|---|---|
| PWM | D2-D13 | D2-D13 | D2-D13 |
| FL EN (LHY / LHL / LKL) | D22 / D24 / D26 | D22 / D23 / D24 | D22 / D23 / D24 |
| FR EN (RHY / RHL / RKL) | D23 / D25 / D27 | D28 / D26 / D27 | D28 / D26 / D27 |
| HallA1-6 | D50, D51, D52, A12, A13, A14 (PCINT0+2) | none | D37, D36, D35, D32, D33, D34 (PCINT1) |

- **Arduino IDE:** open **`firmware/arduino/arduino.ino`**, set **Board → Arduino Mega 2560**, choose the correct **Port**, set **`KRABBY_PIN_REV`** in **`board_pins.h`** if needed, then **Upload**. The serial monitor at **250000** baud (`BAUD_RATE` in `arduino.ino`) should show **`PINS_REV3_UNO_V02`** (or the matching label) after reset.
- **Make + arduino-cli:** install [arduino-cli](https://arduino.github.io/arduino-cli/latest/installation/) and **GNU Make**. On Windows: `winget install GnuWin32.Make` then add **`C:\Program Files (x86)\GnuWin32\bin`** to your **`PATH`**. Put **arduino-cli** on your **`PATH`** (or set **`ARDUINO_CLI`**). Install **pyserial** for port auto-detect: `pip install -r firmware/requirements.txt`. From **`krabby-research`**:
  - `make -C firmware upload-firmware` — auto-detects serial port via **`firmware/mcu_port.default_port()`**. Pass **`PORT=COM5`** (or `/dev/ttyACM0`) to override.
  - Other revisions: `make -C firmware upload-firmware PIN_REV=1` (or `PIN_REV=2`).
  - Compile only: `make -C firmware compile-firmware`.
  - See **`firmware/Makefile`** for **`ARDUINO_CLI`**, **`FQBN`**, **`PIN_REV`**.

Flash each Mega with the image that matches **that** board’s wiring. All three boards use the same sketch; role is elected at runtime.

#### Remote flashing over SSH (boards on another host)

When the USB hub is plugged into a **different machine** than the one you build on — e.g. a Jetson Orin you reach over SSH — use **`flash-remote`**. It compiles locally (where the arduino-cli toolchain lives), copies the `.hex` to the remote, and runs **`avrdude`** there against the board's serial port. No S3 publish and no Docker image needed; it flashes your exact working-tree build.

```bash
# from the build machine (REMOTE = any ssh target; PORT = the device ON the remote)
make -C firmware flash-remote REMOTE=user@orin PORT=/dev/ttyACM0
make -C firmware flash-remote REMOTE=orin PORT=/dev/ttyACM0 PIN_REV=1
```

One-time setup on the remote: `sudo apt install avrdude` and make sure your user can open the port (add to the `dialout` group). Flash the three boards one at a time, passing each board's `PORT` (find them with `krabby firmware show`, or `ls /dev/ttyACM*` / `ls /dev/ttyUSB*` on the remote). Overridable knobs: `AVRDUDE`, `SSH`, `SCP`, `REMOTE_HEX` (staging path on the remote) — see `firmware/Makefile`.

This is distinct from `krabby firmware update` (which downloads a **published** HEX from S3) — `flash-remote` flashes a **local, unpublished** build.

### 2.4 Python SDK

1. From **`krabby-research`**, install dependencies: `pip install -r firmware/requirements.txt`.
2. Ensure **`firmware/interfaces/`** is importable (e.g. run **`python -m firmware`** from **`krabby-research`** as in §3).

---

## 3. Usage Guide

Run the interactive MCU menu from the **krabby-research** directory:

```bash
# On Linux/Mac, you may need sudo for keyboard access
python -m firmware
```

For troubleshooting (verbose telemetry):
```bash
python -m firmware --debug
```


### EEPROM address layout

| Address | Size | Purpose |
|---------|------|---------|
| 0–25 | 26 bytes | `CalData` struct — calibration min/max for 6 actuators + magic word (`0xDEADBEEF`) |
| 26–31 | 6 bytes | Reserved (alignment gap) |
| 32 | 1 byte | Role magic sentinel (`0xAB`) — written once after first successful role election |
| 33 | 1 byte | `BoardRole` value: `1`=FRONT, `2`=LEFT, `3`=RIGHT |

The role bytes survive power cycles. On each boot, the board prints `ROLE_HINT: LEFT/RIGHT/FRONT` immediately before the 3-second role-election window. `krabby-firmware show` reads this hint so follower boards can be labeled correctly even when probed individually (when they would otherwise appear as `ROLE_UNKNOWN` and show as "front").

Role bytes are only written when a valid role is elected (FRONT, LEFT, or RIGHT). A board that times out as ROLE_UNKNOWN does not update EEPROM, preserving the last valid role.

### Feature 1: Auto-Calibration (Run Once)
The robot now calibrates itself automatically and saves limits to EEPROM.
 - Select Option 2 (Auto-Calibrate) in the menu.
 - Stand Back: The robot will perform the safety sequence:
    - Yaw Left -> Yaw Right -> Hip Up -> Knee Out -> Knee In -> Hip Down.
 - Result: Limits are saved. You do not need to repeat this after rebooting.

### Feature 2: Manual Jog Mode
 - Select Option 3 (Jog Mode).
 - Type the joint name (e.g., LHY or LKL).
 - Hold 'W' to Extend, Hold 'S' to Retract.
 - Release keys to stop immediately.

### Feature 3: Neutral Pose
 - Select Option 1.
 - Robot moves all joints to center (0.5). Useful to verify calibration accuracy.

---

## 4. Firmware Store (`krabby-firmware-public`)

Built firmware lives in a public S3 bucket. CI publishes a new build on every push to `mainline` or `release/*`, plus a daily scheduled build of the newest `release/*` branch.

### 4.1 Bucket layout

```
s3://krabby-firmware-public/
  index.json                               ← all branches, latest build per branch
  <branch>/latest.json                     ← pointer to the most recent build on <branch>
  <branch>/builds.json                     ← full build history for <branch> (powers `show <branch>`)
  <branch>/<YYYYMMDD-HHMMSS-<sha7>>/
    firmware.hex                           ← compiled Arduino HEX
    manifest.json                          ← branch, commit, timestamp, board FQBN, VER string
```

`<branch>` mirrors the Git branch name (`mainline`, `release/0.2.0`, etc.).

**`manifest.json` fields:** `schema_version`, `branch`, `commit`, `commit_date`, `build_timestamp`, `board_fqbn`, `ver_string`, `hex_filename`.

### 4.2 V protocol

Send `V\n` on the main serial (250000 baud). The leader board collects replies from all three boards and responds with a single line:

```
VER <versions> <branches> <commits>
```

Each field is `front|left|right` pipe-delimited. Example:

```
VER 0.2.0|0.2.0|0.2.0 release/0.2.0|release/0.2.0|release/0.2.0 abc1234|def5678|ghi9012
```

If a follower board is missing, its slot contains `-`.

### 4.3 Three-board update procedure

```bash
# 1. One-time host setup (udev rules, dialout group, flash tools)
sudo krabby-firmware install

# 2. Check attached boards and the latest build per branch
krabby-firmware show

# 2b. List one branch's full build history, newest-first (paged via $PAGER)
krabby-firmware show release/0.2.0

# 3. Flash all three boards in turn (replug USB between boards)
krabby-firmware update                        # latest release/* build, auto-detects port
krabby-firmware update release/0.2.0          # specific branch
krabby-firmware update /dev/ttyACM1           # specific port, latest release
krabby-firmware update release/0.2.0 /dev/ttyACM2  # specific branch + port
```

Downloaded HEX files are cached under `~/.cache/krabby-firmware/<branch>/<sha7>/firmware.hex` and reused on subsequent calls.

### `krabby-firmware` vs `krabby firmware`

Two ways to reach the same flash CLI:

- **`krabby-firmware <args>`** — runs the flash tool **directly on the host**. Requires the
  `krabby-firmware` package and host flash tools (`krabby-firmware install` sets up
  `avrdude`/`arduino-cli`, udev, and `dialout`). Use this on a laptop or bench machine.
- **`krabby firmware <args>`** — runs that same CLI **inside the locomotion image** (the
  flash tools are bundled there), so a kit owner who only `pip install krabby-launcher`
  can flash with no host setup. It forwards every argument verbatim, mounts the
  `~/.cache/krabby-firmware` download cache, and passes the serial devices through.

So `krabby firmware show release/0.2.0` and `krabby-firmware show release/0.2.0` behave
identically — they differ only in *where* the tool runs.
---

## I2C Sensor Cluster (Milestone 16) — BMI270 IMU

The **leader board only** (role `FRONT` after election, or the solo-board `UNKWN`
bench case) carries a shared I2C bus on the Mega's hardware I2C pins. Followers
never initialize the bus. All bus constants live in `arduino/sensors_config.h`.

### Wiring (SparkFun BMI270 Qwiic breakout, via Qwiic→Dupont adapter)

| Qwiic wire | Mega pin | Note |
| :--- | :--- | :--- |
| VCC (red) | **3.3V** | BMI270 is a 3.3 V part — never 5 V |
| GND (black) | GND | |
| SDA (blue) | **D20** | Mega hardware I2C SDA |
| SCL (yellow) | **D21** | Mega hardware I2C SCL |

- I2C address **0x68** (0x69 with the address jumper cut). Bus runs at **100 kHz**
  for noise margin; the payload per 50 ms telemetry tick is tiny.
- Later sensors (Qwiic OLED, INA228 ×2) daisy-chain on the same bus.

### Telemetry segment

The leader appends one segment to its own telemetry line (append-only; old
parsers drop it — see `firmware/interfaces/joint_telemetry.py`):

```text
;IMU <accel_x> <accel_y> <accel_z> <gyro_x> <gyro_y> <gyro_z> <temp_c> <valid>
```

Units: accel **m/s²**, gyro **rad/s** (gyro is boot-bias-subtracted), temp **°C**.
`valid` is `0` when the sensor did not respond that tick (init failure ships
zeros with `valid=0` and never stalls the gait loop). A failed temperature
read (separate I2C transaction) prints `nan`; the Python parser drops
non-finite segments, so that tick's IMU sample is skipped rather than
shipping a plausible-looking `0.0` °C.

### Axis convention / sensor→body transform

`body[i] = IMU_AXIS_SIGN[i] * sensor[IMU_AXIS_SRC[i]]` (`sensors_config.h`).
**Currently identity** — the breakout's mounting orientation is not final.
Update the constants and this section together when the mount is fixed.

### Boot calibration (EEPROM)

Gyro zero-rate bias is captured at first boot while the robot is stationary
(200 samples, ~1 s), persisted to EEPROM, and reloaded on every subsequent
boot. If motion is detected during capture (gyro spread >
`IMU_CAL_MAX_SPREAD_DPS`), nothing is saved and the capture retries on the
next boot. To force a re-capture, invalidate the magic byte.

Two terms, defined once: the **magic byte** is a sentinel value (`0xC7` here)
whose only job is to prove this EEPROM region was ever written by this
firmware — a factory-fresh AVR reads `0xFF` at every EEPROM address, so
anything other than the expected magic means "no calibration stored; capture
one". The **schema byte** is a layout version number: if a future firmware
changes the field layout of `ImuCalData`, it bumps the schema, and old data
is rejected as stale instead of being silently misread field-by-field.

Full EEPROM map after M16 Task 1. Every address below is a byte offset into
the 4 KB EEPROM, ranges inclusive. Bytes 0–33 are the pre-existing layout
(same as the "EEPROM address layout" table earlier in this file); M16 adds
only bytes 40–65. Constants live in `sensors_config.h`; the `ImuCalData`
struct lives in `arduino.ino`.

| Bytes | Size | Owner | Contents |
| :--- | ---: | :--- | :--- |
| 0–25 | 26 | Joint calibration (`CalData`, pre-existing) | per-actuator min/max for 6 actuators + magic word `0xDEADBEEF` |
| 26–31 | 6 | — | unused (pre-existing alignment gap) |
| 32 | 1 | Role election (pre-existing, M14) | role magic sentinel `0xAB` |
| 33 | 1 | Role election (pre-existing, M14) | `BoardRole` value (1=FRONT, 2=LEFT, 3=RIGHT) |
| 34–39 | 6 | — | unused gap left before the M16 block |
| 40 | 1 | `ImuCalData.magic` | `0xC7` (`EEPROM_IMU_CAL_MAGIC`) |
| 41 | 1 | `ImuCalData.schema` | layout version, currently `1` (`EEPROM_IMU_CAL_SCHEMA`) |
| 42–53 | 12 | `ImuCalData.gyroBiasDps[3]` | 3 × 4-byte float; gyro zero-rate bias, deg/s, raw sensor frame |
| 54–65 | 12 | `ImuCalData.accelBiasG[3]` | 3 × 4-byte float; accel offset, g, raw sensor frame — all zeros today (see the comment on the struct in `arduino.ino`) |
| 66– | — | free | `EEPROM_SENSOR_CAL_NEXT_ADDR` = 66; Task 3 (INA228 cal) and later blocks allocate from here, each with its own magic + schema |

So "`ImuCalData` is 26 bytes" means exactly bytes 40–65:
1 (magic) + 1 (schema) + 12 (gyro bias) + 12 (accel bias) = 26. A
`static_assert` next to the struct in `arduino.ino` pins
`sizeof(ImuCalData)` to `EEPROM_IMU_CAL_SIZE` at compile time, so the table
above cannot silently drift from the code.

### Loop timing (AC 1c) and serial budget

**Motivation:** the IMU adds two per-tick costs — blocking I2C time inside
the 50 ms telemetry tick, and extra bytes on a serial link that was already
near saturation at 115200 baud — so this section derives both costs from the
code, then checks the arithmetic against bench measurements.

Per-tick I2C cost added by the IMU, counted transaction-by-transaction from
the patched driver (`getSensorData` → `bmi2_get_regs(0x03, …, 24)`, then
`getTemperature` → `bmi2_get_regs(0x22, …, 2)`; each register read is a
pointer-write transaction followed by a read transaction — the wrapper's
`endTransmission()` sends a STOP, so these are two plain transactions, not a
repeated start; the wire byte count is the same either way). One wire byte =
8 data bits + 1 ACK = 9 bit-times = 90 µs at 100 kHz:

| Transaction | Wire bytes | Time |
| :--- | ---: | ---: |
| Set register pointer 0x03 (addr+W, reg) | 2 | 180 µs |
| Read STATUS+DATA+SENSORTIME (addr+R, 24 data) | 25 | 2250 µs |
| Set register pointer 0x22 (addr+W, reg) | 2 | 180 µs |
| Read temperature (addr+R, 2 data) | 3 | 270 µs |
| Driver delay after each read (`bmi2_get_regs`; the driver's advance-power-save flag stays set after init) | — | 2 × 450 µs |
| **Floor per tick** | **32** | **3780 µs** |

Measured: ≈4 ms. The ~0.2 ms residual is START/STOP conditions plus AVR Wire
ISR overhead, which are not derivable from code. The longest single blocking
transaction is the 25-byte read ≈ 2.25 ms — a 4.4× margin under
`I2C_WIRE_TIMEOUT_US` (10 ms), which bounds each blocking transfer
individually.

The `;IMU` segment adds **49–63 characters** to the leader's line: exactly 49
on the all-zeros `valid=0` path (which is the measured 229 − 180 = 49 below),
up to 63 with every field at its widest (accel `-78.453` at the ±8 g default
range, gyro `-69.8132` worst case, temp `-41.0`). The field-by-field
derivation of the 49 and 63 figures (float-formatting rules and the value
bound behind each width) lives in `docs/M16-DESIGN-DECISIONS.md` §1.1.1 (companion docs PR); the
I2C wire math is the table above.

At the old 115200 baud the upstream link budget was 11520 B/s × 50 ms =
576 B per tick. Three lines per tick at the bench-measured 180 B = 540 B
(94%) before M16; adding the 49 B IMU segment makes 589 B (102%) — over
budget, with the blocking `flush()` stretching the tick and the hall
counters growing every line. `BAUD_RATE` is now **250000** (exact 0%-error
divider on the 16 MHz Mega), giving 1250 B/tick — 589 B nominal = 47%
utilization (per-field line derivation in the byte-accounting comment next
to `TELEMETRY_LINE_MAX` in `arduino.ino`). Host-side defaults in
`krabby_mcu.py`, `gui/app.py`, `gui/__main__.py`, the `cli.py` V-probe, and
the Jetson HAL (`hal/server/jetson/krabby_mcusdk.py`, `hal_server.py`)
match; the avrdude *bootloader* baud (Makefile / `cli.py` flash path) is
separate and stays 115200.

Bench evidence — captured 2026-07-06 on a solo Mega 2560 R3 (ROLE_UNKNOWN
bench leader, 400 lines per row, host-side inter-line arrival timestamps):

| Build | line len (B) | mean tick (ms) | p95 (ms) | max (ms) |
| :--- | :--- | :--- | :--- | :--- |
| upstream/main @ 115200 | 180 | 50.72 | 53.29 | 57.09 |
| M16 Task 1 @ 250000, IMU absent (valid=0 path) | 229 | 50.77 | 53.38 | 58.84 |
| M16 Task 1 @ 250000, IMU attached | _TBD_ | _TBD_ | _TBD_ | _TBD_ |

Delta with the IMU segment added: **+0.05 ms mean** — inside run-to-run
noise, satisfying "no measurable change to loop timing" for the serial path.
The IMU-attached row (adds the live ~4 ms I2C read inside the tick) and a
full three-board `tests/integration/test_timing.py` run are captured at
robot integration.

### Bench bring-up runbook (M16, solo board)

> Formal ATP-style test procedures (with run logs and an AC traceability matrix) live in `firmware/bench_tests/INDEX.md` (companion docs PR); this runbook is the narrative version.

Replicated 2026-07-06 at a café table. Everything below assumes the repo venv
(`testenv`) has `pyserial`, and `PORT` = the board's device (macOS:
`ls /dev/cu.usbmodem*`; if nothing appears but the board is powered, check the
"Allow accessory to connect" gate in System Settings → Privacy & Security —
the Mega enumerates but gets no serial driver until allowed).

1. **Voltage check (before first sensor connect).** Meter probes don't fit
   female headers: plant two M-M Dupont jumpers in `3V3` and `GND` and probe
   their free ends (don't let them touch). Expect 3.30 ± 0.1 V. The BMI270 is
   **not 5 V tolerant** — this check is the one that saves the sensor.
2. **Wire (USB unplugged).** Qwiic→Dupont: black→GND, red→3V3, blue→D20 (SDA),
   yellow→D21 (SCL). Either Qwiic jack on the breakout works.
3. **Flash + watch boot.** `make -C firmware upload-firmware PORT=$PORT`, then
   `python firmware/scripts/imu_bench.py $PORT watch`. Expected boot on a solo
   board: `ROLE: UNKNOWN (front actuators)` (the bench-leader case), then
   `IMU CAL: BMI270 online at 0x69` — **the M16 unit's ADR jumper is cut**, so
   it answers on the alternate address; firmware probes 0x68 then 0x69. First
   boot: `gyro bias captured and saved to EEPROM` (board must sit still ~1 s;
   `motion detected` means it retries next boot). Later boots:
   `loaded from EEPROM`.
4. **Verify.** At rest `|accel| ≈ 9.81 m/s²` and gyro ≈ 0 (bias-subtracted).
   Then `imu_bench.py $PORT flip` — flip the **breakout board itself** (not
   the Mega; the sensor is the thing at the end of the cable) upside down and
   hold ~10 s: PASS requires inverted samples. The mode exists because a
   remote-guided test needs a *confirmed* physical action — assume nothing.
5. **Timing evidence (AC 1c).** `imu_bench.py $PORT timing` with the board
   still; numbers land in the table above.
6. **Bus debugging ladder** (when init fails): flash
   `bench_sketches/i2c_scanner` — idle SDA/SCL must both read 1; a found
   address ≠ expected means jumper strap; found-but-init-fails means driver
   timing/data (see patches 2 and 4 in the fetched-libraries section below).
   Reflash real firmware afterwards.

Note: opening the serial port resets the board (macOS pulses DTR on open
regardless of pyserial settings) — every capture in `imu_bench.py` waits
through the ~4 s boot for this reason. `krabby_mcu.connect()` avoids the
reset with its pre-open `dtr = False` on Linux/Jetson, but macOS resets anyway.

### Fetched libraries (AVR patches)

Third-party Arduino libraries are **not committed**. `make compile-firmware`
(and CI) first runs `scripts/fetch_arduino_libs.py`, which downloads the
pinned upstream release (SparkFun BMI270 `v1.0.3` =
`21ea234de321da07c552f7a43cb36f7df4f73a27`, MIT), verifies the archive's
SHA-256, unpacks it into the gitignored `arduino/libraries/`, and applies the
committed delta `arduino/patches/SparkFun_BMI270_Arduino_Library.patch`. The
first fetch needs network once (~2.7 MB); every later build is offline (a
stamp file guards re-fetching, and a pin or patch change invalidates it).
Design rationale and alternatives: `docs/M16-DESIGN-DECISIONS.md` §2.1 (companion docs PR).

The patch carries four AVR fixes, all tagged `Krabby patch` in-source:

1. **PROGMEM config blob** — Bosch's ~8 KB config blob is placed in flash and
   staged through RAM during init upload (`bmi270.c`,
   `bmi2.c:upload_file`). Unpatched, the blob lands in SRAM and the Mega
   (8 KB total) cannot link.
2. **16-byte config chunks** — `sensor.read_write_len` lowered 32 → 16 in
   `BMI270::begin()` (`SparkFun_BMI270_Arduino_Library.cpp`). Each config
   chunk is one I2C write of 1 register byte + N data bytes against AVR
   Wire's 32-byte TX buffer, so N=32 silently drops the last byte of every
   chunk and config load fails; N must be even and ≤ 30, and 16 divides the
   8192-byte blob evenly.
3. **Short-read detection** — `readRegistersI2C` fails on a short
   `requestFrom()` instead of returning OK with a stale buffer
   (`SparkFun_BMI270_Arduino_Library.cpp`).
4. **usDelay overflow** — AVR's `delayMicroseconds()` is only valid to
   16383 µs; the driver waits up to 51 ms through it (including the ~20 ms
   config-validation wait), so the bare upstream call makes `bmi270_init`
   fail with `BMI2_E_CONFIG_LOAD` (-9) on every boot. The patch splits the
   wait into `delay(ms)` + `delayMicroseconds(remainder)`. Found on the
   bench 2026-07-06: the sensor ACKed and returned its chip ID, config bytes
   round-tripped perfectly, and init still failed — the last suspect standing
   was time itself. `make`/CI builds always use the fetched, patched copy —
arduino-cli's `--libraries` outranks sketchbook libraries — so a globally
installed upstream copy cannot shadow it there. The **Arduino IDE** is the
exception: it does not scan sketch-local `libraries/`, so an IDE build fails
to find the header, and installing the upstream library via Library Manager
instead builds the unpatched version, whose ~8 KB config blob overflows the
Mega's SRAM at link time. To build from the IDE, materialize the library
once, then symlink it into your sketchbook (and do not also install the
upstream library):

```sh
python3 scripts/fetch_arduino_libs.py   # one-time; make compile-firmware also runs this
ln -s "$(pwd)/arduino/libraries/SparkFun_BMI270_Arduino_Library" ~/Documents/Arduino/libraries/
```

Otherwise prefer `make compile-firmware` / `make upload-firmware`.
