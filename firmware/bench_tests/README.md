# bench_tests

Bench procedures for the acceptance criteria that cannot be closed by reading code
or running the native suite.

Two layers, deliberately separate:

- **`checks.py` — atomic checks.** One measurement each, no criterion attached.
  Runnable on their own for exploration.
- **`task1.py` — criteria.** Each composes checks and adds the threshold that turns
  a measurement into a verdict, with the requirement text quoted from the review
  spec.

Companion to `firmware/bench_sketches/`, which holds standalone flashable sketches.

## Running

```bash
python3 -m firmware.bench_tests list

# one atomic check — prints the measurement, no pass/fail
python3 -m firmware.bench_tests check timing --port /dev/cu.usbmodem2101
python3 -m firmware.bench_tests check flip   --port /dev/cu.usbmodem2101

# the composed suite: interactive, resumable
python3 -m firmware.bench_tests run --port /dev/cu.usbmodem2101
python3 -m firmware.bench_tests run --port /dev/cu.usbmodem2101 --only 1g.1 1c.4
```

The GUI holds the serial port exclusively — close it first
(`pkill -f firmware.gui`).

## Supersedes `firmware/scripts/imu_bench.py`

| imu_bench | here |
|---|---|
| `PORT timing` | `check timing` |
| `PORT watch` | `check stream` |
| `PORT flip` | `check flip`, and criterion `1i.2` |

Thresholds are kept identical where they overlap — `flip` still gates on accel-Z
below −3 and passes above 20 inverted samples — so results stay comparable to
anything recorded with the older tool.

## Resuming

Results are written to `bench-results-task1.json` after **every** test, so an
interrupted session loses nothing. On the next `run` the selector lists prior
results and puts the cursor on the first test that has not passed — which is the
resume point for an ordered suite, whether the reason is a failure or a test never
reached. Pick any number to start elsewhere, or `a` to redo from the top.

Pass `--results PATH` to keep separate files per board or per session.

## Ordering

The default order is deliberate:

1. `1a.*` — wiring inspection, nothing flashed
2. `e2e.1`, `e2e.2`, `1i.2`, `1e.4` — one continuous sensor-attached sequence
3. `1g.1` ×2, `1g.4` — calibration; `1g.4` needs a stored bias, so it follows
4. `1b.5`, `1c.4` — last, because they need the sensor unplugged

`--only` respects declaration order, not the order you type.

## Two entries, one criterion

`1g.1` appears twice: a stationary capture and a moving negative control. The spec
folds both into one criterion's pass condition, and they run the same code under
different guidance — that is what makes it a control. Each has its own `key`
(`1g.1-stationary`, `1g.1-moving`) so results record separately while both report
against `1g.1`.

## Tests that clear stored calibration

`1g.1` (both) are marked `[clears stored cal]`. The firmware has no command for
this: `calibrate()` returns `Loaded` whenever EEPROM holds a valid record, so the
capture path is unreachable while one exists.

`cal.invalidate()` flashes `bench_sketches/imu_cal_clear`, which writes `0x00` over
the magic byte at `EEPROM_IMU_CAL_ADDR`, then restores the real firmware via
`make upload-firmware`. Joint calibration (bytes 0–25) and role (32–33) are
untouched. Each costs two flash cycles, roughly 40 s.

## Notes for the operator

**The sensor is only probed at boot.** Plugging the IMU back in without a reset
leaves `imu_valid=0` and zeros on the wire; it does not recover live. Unplugging a
running one gives the same zeros. "Plugged in" and "working" only coincide after a
reset.

**The `;IMU` segment is always emitted.** `appendImuMeasurement` is called
unconditionally on the leader, so an absent sensor produces
`;IMU 0.000 0.000 0.000 0.0000 0.0000 0.0000 0.0 0` rather than no segment. Judge
presence by the `valid` flag, not by whether the segment is there.

**`1g.1-moving` needs sustained motion.** The capture window is
`IMU_CAL_SAMPLES × IMU_CAL_SAMPLE_INTERVAL_MS` — about one second — and rejection
is on `max − min` across it. A brief shake is caught, but stopping before the window
opens is not motion at all. Keep moving from before the prompt until after
"Krabby Ready".
