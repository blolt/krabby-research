# Shared native Wire substitute

`wire_native_support` provides the single `Wire.h`, `TwoWire` implementation and
global `Wire` for the IMU, OLED, INA adapter and power-poll tests. It has no Unity,
Arduino clock/GPIO, or vendor-driver dependency. CMake exposes its include path
only to targets that link it.

Each bus owns its state by default. A fixture can instead pass a
`wire_native::State&` to share its scripts and observations with an environment.
The state must outlive the bus. Queue `Transfer` objects in transaction order;
each names its expected device address. Wrong addresses and unscripted operations
are recorded in `errors` and must be checked by the caller. Also check that
`transfers` is empty when the scenario finishes.

```cpp
TwoWire bus;
wire_native::Transfer sample;
sample.address = 0x6B;
sample.bytes = {0x01, 0x02};
sample.reported = 2;
bus.state().transfers.push_back(sample);
// Pass bus to the real adapter and invoke its operation.
```

A register write ending without STOP and the following request share one scripted
transfer. A standalone request consumes a new transfer. Scripted write counts,
ACK/NACK status, timeout flags, reported read counts and actual receive bytes are
independent so tests can inject acquisition failures and inconsistent reads.
An ACK does not clear a previously set timeout flag; clear it explicitly through
the Wire API. The fake records the requested address, write bytes, STOP flags and
read counts for protocol assertions. A buffered `write(data, length)` is recorded
byte by byte and returns the sum of the per-byte scripted counts. The fake does
not emulate registers or electrical timing, enforce a hardware buffer size, or
simulate GPIO bus clearing.

Clock, timeout configuration, initialization state, scripts, errors and events are
per bus. `reset()` clears all fake state, including the observer and active read.
An optional event observer lets existing suites preserve their combined ordering
of bus, driver and GPIO events. Device-specific data lives in driver support,
outside this transport implementation.

A test can attach a `wire_native::Device` at an address through `state().devices`.
Every transaction to that address then goes to the device instead of the script
queue: `endTransmission` passes the bytes written since `beginTransmission` to
`transmit`, whose return value is the status (5 also sets the timeout flag), and
`requestFrom` returns what `receive` supplies, fewer bytes being a short read.
Other addresses keep consuming scripts. `reset()` detaches devices. Register-level
device fakes that answer the real SparkFun drivers live in `fakes/devices/`.

The `test_wire` scenarios cover interleaved buses and addresses, repeated-start
protocol, NACK/timeout independence, short reads and buffer exhaustion, unexpected
operations, and lifecycle/configuration isolation. Existing adapter tests remain
responsible for verifying production behavior.
