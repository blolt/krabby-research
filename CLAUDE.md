# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

Locomotion stack for the Krabby hexapod: firmware (3× Arduino Mega), HAL, RL policy
training/inference, and deployment tooling. `docs/GLOSSARY.md` decodes the project
vocabulary (joint codes, IS, octopus, etc.); `docs/FOLDER_LAYOUT.md` maps directories.

## Commands

```bash
make venv                                  # ./testenv (Python 3.11)
make install-editable                      # one-time: hal/krabby-hal-* editable installs

# Fast tests (no Docker) — the everyday loop:
testenv/bin/python -m pytest tests/unit/firmware -q
testenv/bin/python -m pytest tests/path/test_file.py::test_name   # single test

make test                                  # FULL Dockerized suite (needs Docker + GPU toolkit);
                                           # bare `make` runs this — it is not a build

# Firmware (Arduino Mega 2560):
make -C firmware compile-firmware          # no board needed; use this to verify firmware changes
make -C firmware upload-firmware PORT=/dev/cu.usbmodemXXX
make -C firmware flash-remote REMOTE=user@orin PORT=/dev/ttyACM0

# Bench verification (see firmware/bench_tests/INDEX.md for formal procedures):
testenv/bin/python firmware/scripts/imu_bench.py PORT timing|watch|flip
```

pytest runs with `--import-mode=importlib` and `pythonpath=.`; markers `jetson` and
`isaacsim` gate hardware/sim-dependent tests. Deployment on a robot uses the `krabby`
CLI (`pip install krabby-launcher`; `krabby run`, `krabby firmware update`) — see README.md.

## Architecture

**Two halves sharing one policy runtime.** Training lives in `parkour/` (IsaacLab RL);
the policy runtime `compute/parkour/` is identical across simulation, testing, and
production containers. Production entry point is `python -m hal.server.jetson.main`
(one process on the Orin: HAL server + inference client over inproc ZMQ, plus optional
collector/teleop threads). The HAL boundary (`docs/HAL_GUIDE.md`, ZMQ) is what lets the
same policy drive IsaacSim or real hardware — swap the backend, never the policy.
Diagrams: `docs/RUNTIME_ARCHITECTURE.md`; the MCU→SDK data flow specifically:
`docs/M16-DESIGN-DECISIONS.md` §Information flow.

**Firmware: one sketch, three boards, runtime role election.** All three Megas flash
the identical image (`firmware/arduino/arduino.ino`). At boot they elect roles over the
follower UARTs: the board that hears both siblings becomes FRONT (the leader, on USB to
the Orin) and assigns LEFT/RIGHT. A solo board on USB elects ROLE_UNKNOWN and acts as a
bench leader. The leader forwards follower telemetry lines verbatim and appends its own
sensor segments (`;IMU ...`) to its own line only. **Role-election code is milestone
M14 (another contractor) — do not modify it.**

**The telemetry wire contract is append-only** and defined in three places that must
change together: `firmware/arduino/actuator_manager.h` + `arduino.ino` (emit),
`firmware/interfaces/joint_telemetry.py` (parse), `tests/unit/firmware/` (pin). Parsers
ignore unknown segments; never rely on segment order or count beyond the spec in
`docs/M16-DESIGN-DECISIONS.md` §Interfaces.

**Serial link: 250000 baud, one `#define` (`BAUD_RATE` in arduino.ino), six host-side
sites that must match** (enumerated in `docs/M16-DESIGN-DECISIONS.md`). The avrdude
bootloader flash baud (115200) is a separate protocol — leave it. Changing any shared
protocol constant requires a repo-wide grep for the old value; the production Jetson
HAL is the consumer most easily missed.

**EEPROM is allocated by convention**: hand-assigned regions, each with a magic byte +
schema version. New persistent state allocates from `EEPROM_SENSOR_CAL_NEXT_ADDR`
(`firmware/arduino/sensors_config.h`); the byte map lives in `firmware/SETUP.md`.

**Publishing**: CI builds firmware to S3 and container images to ECR
(`docs/PUBLISHING.md`); a bench watchdog (`bench/`) smoke-tests new images.

## Conventions and traps

- **AVR constraints (Mega 2560: 8 KB SRAM, Harvard arch).** Watch `Global variables use`
  on every firmware compile. New I2C/driver libraries almost always need patches:
  PROGMEM for const blobs, transactions ≤ 32-byte Wire buffers, `delayMicroseconds()`
  overflows above 16383 µs. The BMI270 patch set (`firmware/arduino/patches/`, tagged
  `Krabby patch`) is the worked example; library source is never committed — the build
  materializes pinned+patched libraries into gitignored `firmware/arduino/libraries/`
  via `firmware/scripts/fetch_arduino_libs.py` (design: `docs/M16-DESIGN-DECISIONS.md`
  §2.1) and passes `--libraries` — never install the upstream SparkFun BMI270 library
  globally.
- **Design docs precede code** and live in `docs/` on the feature branch: written as if
  before implementation, commit-agnostic references, decisions scored against the
  tensions rubric in `docs/M16-DESIGN-DECISIONS.md`'s preamble (functionality,
  maintenance, correctness, efficiency, readability, extensibility, simplicity, and
  above all reversibility).
- **Host-side error handling** follows `docs/M16-ERROR-HANDLING.md`: expected per-line
  parse failures return `Optional` with counted reasons + throttled logging; init
  failures carry actionable reasons (`sdk.last_error` pattern); absence-by-design
  (follower has no IMU) is silent. Don't collapse these three classes into one path.
- **Bench work is procedural**: every hardware-verifying change gets an ATP in
  `firmware/bench_tests/` (template in INDEX.md) and every run — including failures —
  appends to the TP's run log. Remote-guided physical tests must be binary and
  verifiable in the data.
- **Test naming**: `test_<unit>_<condition>_<expected>`, arrange-act-assert body
  structure (`tests/unit/firmware/test_imu_telemetry.py` module docstring).
- **Known hazard**: single-byte serial commands are noise-triggerable
  (`docs/HAZARD-SERIAL-COMMAND-NOISE.md`, tracked as issue #2); coordinate any command-
  protocol change with the upstream `m17` noise-ingress work.
- Opening the leader's serial port resets the board (DTR); host code that must not
  reset it uses the pre-open `dtr = False` pattern in `krabby_mcu.connect()` (does not
  hold on macOS — expect a reset there).
