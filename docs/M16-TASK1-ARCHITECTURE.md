# M16 Task 1 architecture

This note records the functional-core / imperative-shell boundaries introduced
by the Task 1 review.

## Firmware ownership

The hardware-independent `imu` module owns calibration math, EEPROM-record
validation, body-axis mapping, bad-read state transitions, and telemetry
serialization. All mutable behavior is visible through an explicit
`imu::State` argument.

The concrete `lsm6dso` device module owns Wire setup, address probing, checked
SparkFun configuration, the coherent 14-byte register read, and device-specific
unit conversion. `arduino.ino` explicitly composes the device, state, delay,
EEPROM function-table port, and output. There is no runtime layer, virtual
device hierarchy, or manager object.

```text
firmware/arduino/
├── arduino.ino                   composition and loop orchestration
├── units.h                       physical quantity wrappers
└── src
    ├── constants
    │   ├── imu_constants.h       calibration and state-transition constants
    │   └── telemetry_constants.h Arduino-to-host wire tokens
    ├── devices
    │   ├── lsm6dso.h
    │   └── lsm6dso.cpp           concrete Wire/SparkFun shell
    └── imu
        └── imu.h / imu.cpp       functional core and explicit state
```

The runtime path is:

```text
setup
└── imuSetup
    ├── lsm6dso::initialize
    │   ├── Wire::begin / setClock / setWireTimeout
    │   ├── LSM6DSO::begin (primary, then alternate address)
    │   └── checked register configuration
    ├── imu::calibrationPlausible
    ├── imu::addCalibrationSample / finalizeCalibration
    └── imu::persistCalibration (invalid record → valid magic → verify)

loop
├── sensorReading = lsm6dso::read (one 14-byte burst)
├── measurement = imu::processReading(state, sensorReading)
└── imu::appendTelemetry(output, measurement)
```

Native C++ tests compile the production `imu.cpp` directly. They exercise the
functional state transitions and a recording implementation of the EEPROM
function table. The concrete Wire/SparkFun module remains an on-target
component boundary.

## Host ownership and call stack

```text
firmware/
├── krabby_mcu.py
│   └── KrabbyMCUSDK            serial lifecycle and latest-sample storage
├── interfaces/
│   ├── telemetry_parser.py     line/segment routing and aggregate parse result
│   ├── parsed_telemetry.py     complete parsed-line value
│   ├── joint_telemetry.py      joint value and joint-token parser
│   ├── imu_telemetry.py        IMU value and IMU-token parser
│   └── telemetry_constants.py  host wire tokens and size limit
└── gui/app.py
    └── ImuRow                  IMU freshness, latching, and presentation
```

The generated host call graph remains
[`architecture/m16-task1-host-callgraph.svg`](architecture/m16-task1-host-callgraph.svg).
