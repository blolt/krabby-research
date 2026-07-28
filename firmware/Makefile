# Krabby Arduino Mega 2560 firmware — compile and upload via arduino-cli.
#
# Usage (from krabby-research):
#   make -C firmware upload-firmware
#   make -C firmware upload-firmware PORT=COM5
#   make -C firmware upload-firmware PIN_REV=1
#   make -C firmware compile-firmware          # compile only, no upload
#
# Remote flashing (boards on another host you reach over SSH, e.g. a Jetson Orin
# with the USB hub): compile here, copy the .hex over, run avrdude on the remote.
#   make -C firmware flash-remote REMOTE=user@orin PORT=/dev/ttyACM0
#   make -C firmware flash-remote REMOTE=orin PORT=/dev/ttyACM0 PIN_REV=1
# PORT is the serial device *on REMOTE*; the remote needs avrdude installed
# (apt install avrdude) and permission on the port (dialout group). Flash boards
# one at a time, passing each board's PORT.
#
# Prerequisites: arduino-cli on PATH, pyserial for auto-detect (pip install pyserial).
# Windows: winget install GnuWin32.Make, then add GnuWin32\bin to PATH.

ARDUINO_CLI ?= arduino-cli
CMAKE       ?= cmake
CTEST       ?= ctest
PYTEST      ?= pytest
FQBN        ?= arduino:avr:mega
PIN_REV     ?= 3
SKETCH      := $(CURDIR)/arduino

# Remote flashing (flash-remote): compile here, flash on REMOTE via avrdude.
# NOTE: no trailing inline comments on these — make would fold the padding spaces
# into the value and corrupt the .hex path / ssh target.
REMOTE      ?=
AVRDUDE     ?= avrdude
SSH         ?= ssh
SCP         ?= scp
BUILD_DIR   := $(CURDIR)/build
REPO_ROOT   := $(abspath $(CURDIR)/..)
NATIVE_TEST_SOURCE := $(REPO_ROOT)/tests/native/firmware
NATIVE_TEST_BUILD  := $(REPO_ROOT)/build/native-firmware-tests
HEX         := $(BUILD_DIR)/arduino.ino.hex
REMOTE_HEX  ?= /tmp/krabby-firmware.hex

ifeq ($(OS),Windows_NT)
PYTHON ?= python
else
PYTHON ?= python3
endif

# Always bake in the 256-byte serial RX buffer. The leader forwards ~200-byte
# follower telemetry lines from Serial1/Serial2; the AVR core's 64-byte default
# RX buffer drops the middle of those lines and the host logs "can't keep up".
# CI (.github/workflows/publish-firmware.yml) and firmware/install.py's
# platform.local.txt already pass this define; passing it here too makes
# `make compile/upload-firmware` produce an identical binary regardless of
# whether install.py ran, the host OS, or which AVR core version is installed.
# KRABBY_PIN_REV is passed explicitly as well (board_pins.h defaults to 3 when
# undefined, so -DKRABBY_PIN_REV=3 is a harmless no-op for the default build).
BUILD_PROPS := --build-property "compiler.cpp.extra_flags=-DSERIAL_RX_BUFFER_SIZE=256 -DKRABBY_PIN_REV=$(PIN_REV)" \
               --build-property "compiler.c.extra_flags=-DSERIAL_RX_BUFFER_SIZE=256 -DKRABBY_PIN_REV=$(PIN_REV)"

# Auto-detect serial port for upload-firmware (only when PORT not provided).
ifneq ($(filter upload-firmware,$(MAKECMDGOALS)),)
ifeq ($(strip $(PORT)),)
ifeq ($(OS),Windows_NT)
PORT := $(shell $(PYTHON) "$(CURDIR)/scripts/detect_mcu_port.py" 2>NUL)
else
PORT := $(shell $(PYTHON) "$(CURDIR)/scripts/detect_mcu_port.py" 2>/dev/null)
endif
endif
ifeq ($(strip $(PORT)),)
$(error No serial port found. Pass PORT=COMx or install pyserial for auto-detect)
endif
$(info Using PORT=$(PORT))
endif

.PHONY: arduino-core fetch-libs compile-firmware upload-firmware flash-remote test-native test-firmware

test-native:
	$(CMAKE) -S "$(NATIVE_TEST_SOURCE)" -B "$(NATIVE_TEST_BUILD)"
	$(CMAKE) --build "$(NATIVE_TEST_BUILD)"
	$(CTEST) --test-dir "$(NATIVE_TEST_BUILD)" --output-on-failure

test-firmware: test-native
	cd "$(REPO_ROOT)" && $(PYTEST) -q tests/unit/firmware

# Pinned to the core version the bench-verified hex was built with; bump
# deliberately, together with the CI cache key in publish-firmware.yml.
arduino-core:
	$(ARDUINO_CLI) core install arduino:avr@1.8.8

# Third-party Arduino libraries (e.g. SparkFun BMI270 with the Krabby AVR
# patches) are NOT committed: fetch-libs materializes them into the gitignored
# LIBS_DIR from pinned, SHA-256-verified upstream archives plus the committed
# patches in arduino/patches/ (see docs/M16-DESIGN-DECISIONS.md §2.1). The
# script is stamp-guarded — after the first successful fetch every build is
# offline and the recipe is a fast no-op. Passed via --libraries so builds are
# reproducible without any arduino-cli lib install step. The fetch must stay
# inside a recipe (never `$(shell ...)`) so `make -n` stays network-free.
LIBS_DIR := $(SKETCH)/libraries

fetch-libs:
	$(PYTHON) "$(CURDIR)/scripts/fetch_arduino_libs.py"

compile-firmware: arduino-core fetch-libs
	$(ARDUINO_CLI) compile --fqbn $(FQBN) $(BUILD_PROPS) --libraries "$(LIBS_DIR)" --output-dir "$(BUILD_DIR)" $(SKETCH)

upload-firmware: compile-firmware
	$(ARDUINO_CLI) upload -p "$(PORT)" --fqbn $(FQBN) --input-dir "$(BUILD_DIR)" $(SKETCH)

# Flash that same locally-built image onto a board attached to REMOTE over SSH (no
# S3): copy the .hex over and run avrdude there. avrdude -c wiring talks to the stock
# Arduino bootloader, same as cmd_update's _flash().
flash-remote: compile-firmware
	@test -n "$(REMOTE)" || { echo "ERROR: set REMOTE=user@host (the machine the boards are plugged into)"; exit 1; }
	@test -n "$(strip $(PORT))" || { echo "ERROR: set PORT=/dev/ttyACMx (the board's serial device on $(REMOTE))"; exit 1; }
	$(SCP) "$(HEX)" "$(REMOTE):$(REMOTE_HEX)"
	$(SSH) "$(REMOTE)" "$(AVRDUDE) -p m2560 -c wiring -P '$(PORT)' -b 115200 -D -U flash:w:$(REMOTE_HEX):i"
