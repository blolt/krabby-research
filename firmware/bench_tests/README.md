# Task 3 power-monitor bench checks

List the checks without opening a serial port:

```sh
python -m firmware.bench_tests list
```

With the board connected, run the interactive suite or one measurement:

```sh
python -m firmware.bench_tests run --port /dev/ttyACM0
python -m firmware.bench_tests check battery --port /dev/ttyACM0
python -m firmware.bench_tests check ina-reconnect --port /dev/ttyACM0
```

The suite records results in `bench-results-task3.json` and supports `--only`
to select acceptance criteria. Hardware inspections and meter comparisons
require operator input. Make and break power connections with pack protection open.
