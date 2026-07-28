/*
 * Krabby-Uno: 18-Joint Distributed Controller (3 boards × 6 actuators)
 * Front: FL + FR, on USB. Left: RL + ML, on pins 14/15 (Serial3). Right: MR + RR, on pins 16/17 (Serial2).
 * All three boards use the same pinout; role election selects which 6 actuators this board drives.
 */

#include <Arduino.h>
#include <EEPROM.h>
#include <Wire.h>
#include "SparkFunLSM6DSO.h"
#include "imu_init.h"
#include "imu_sample.h"
#include <Adafruit_INA228.h>
#include <SparkFun_Qwiic_OLED.h>
#include <res/qw_fnt_5x7.h>
#include <math.h>
#include "battery_level.h"
#include "battery_split.h"
#include "battery_telemetry.h"
#include "board_pins.h"
#include "command.h"
#include "controller_freshness.h"
#include "controller_slots.h"
#include "disconnect_status.h"
#include "oled_actuator_glyphs.h"
#include "oled_transfer_budget.h"
#include "ina_pack_config.h"
#include "ina_pack_lifecycle.h"
#include "ina_voltage.h"
#include "measurement_units.h"
#include "power_calibration_protocol.h"
#include "power_calibration_storage.h"
#include "actuator_manager.h"
#include "sensors_config.h"
#include "shunt_calibration.h"
#include "telemetry_poll.h"
#include "voltage_calibration.h"
#include "telemetry_protocol.h"
#include "version.h"

// --- Serial: left follower = Serial1 (TX1/RX1 on Krabby-Uno v0.1 shield), right follower = Serial2 ---
#define SERIAL_LEFT  Serial1  // pins 18 (TX1), 19 (RX1) — Krabby-Uno v0.1 shield Serial1 connector
#define SERIAL_RIGHT Serial2   // pins 16 (TX2), 17 (RX2) — Krabby-Uno v0.1 shield Serial2 connector
// 250000 is an exact divider on the 16 MHz Mega (0% baud error, vs 115200's
// +2.1% as deployed); the 16U2 bridge is also 16 MHz so passthrough stays exact.
// Both ends of the follower UART links compile from this same define. The
// avrdude bootloader flash baud (firmware/Makefile, cli.py) is separate — do
// not change it. Per-tick byte budget lives next to TELEMETRY_LINE_MAX.
#define BAUD_RATE 250000
#define SYNC_TOKEN "SYNC"
#define ASSIGN_LEFT  "ROLE:LEFT"
#define ASSIGN_RIGHT "ROLE:RIGHT"

BoardRole currentRole = ROLE_UNKNOWN;

// OLED render state types — defined up here so the .ino auto-prototype pass sees
// them before it hoists prototypes for the render functions (oledGlyph /
// oledRenderKrab) that take them. Constants + bodies live in the render section.
struct OledKrabState {
  bool front, left, right;
  OledGlyph legs[6][3];
  float batteryLevels[2];
  const char *role;
  int roll, pitch;
  float packVoltage;

  // Field-wise equality so oledRenderKrab can skip the erase()+redraw()+display()
  // (a ~120 ms full-frame I2C flush) when nothing drawn changed since last frame.
  // role is compared by pointer: roleName() returns a fixed string literal per
  // role, so equal role == equal pointer (no strcmp needed).
  bool operator==(const OledKrabState &o) const {
    if (front != o.front || left != o.left || right != o.right) return false;
    if (roll != o.roll || pitch != o.pitch) return false;
    if (batteryLevels[0] != o.batteryLevels[0] ||
        batteryLevels[1] != o.batteryLevels[1] ||
        packVoltage != o.packVoltage) return false;
    if (role != o.role) return false;
    for (int i = 0; i < 6; i++)
      for (int j = 0; j < 3; j++)
        if (legs[i][j] != o.legs[i][j]) return false;
    return true;
  }
  bool operator!=(const OledKrabState &o) const { return !(*this == o); }
};

// M16 I2C sensor cluster (IMU; later OLED/power mgmt) is leader-only.
// ROLE_UNKNOWN also qualifies: it is the solo-board-on-USB bench case (defaults
// to front actuators + USB serial), not a follower — followers are assigned
// LEFT/RIGHT during role election.
static inline bool isI2CClusterBoard()
{
    return roleOwnsControllerDisplay(currentRole);
}

// EEPROM address 32: magic sentinel byte (0xAB); address 33: BoardRole value.
// Calibration data (CalData) occupies addresses 0–25; gap at 26–31 kept for alignment.
#define EEPROM_ROLE_ADDR  32
#define EEPROM_ROLE_MAGIC 0xAB

static void saveRole(BoardRole r)
{
    EEPROM.update(EEPROM_ROLE_ADDR,     EEPROM_ROLE_MAGIC);
    EEPROM.update(EEPROM_ROLE_ADDR + 1, (uint8_t)r);
}

static BoardRole loadRole()
{
    if (EEPROM.read(EEPROM_ROLE_ADDR) != EEPROM_ROLE_MAGIC)
        return ROLE_UNKNOWN;
    uint8_t r = EEPROM.read(EEPROM_ROLE_ADDR + 1);
    if (r == ROLE_FRONT || r == ROLE_LEFT || r == ROLE_RIGHT)
        return (BoardRole)r;
    return ROLE_UNKNOWN;
}

static const char* roleName(BoardRole r)
{
    switch (r)
    {
        case ROLE_UNKNOWN: return "UNKWN";
        case ROLE_FRONT:   return "FRONT";
        case ROLE_LEFT:   return "LEFT ";
        case ROLE_RIGHT:  return "RIGHT";
        default:          return "UNKWN";
    }
}

// --- All 18 actuators (names fixed; each board uses the same physical pins for its 6) ---
// Pin numbers from board_pins.h (KRABBY_PIN_REV 1 = legacy, 2 = MOTOR_HEADER_PINOUT).
// Leader/Default Board
LinearActuator flhy("FLHY", PIN_S0_PWMR, PIN_S0_PWML, PIN_S0_EN, A6, A0, 0);
LinearActuator flhl("FLHL", PIN_S1_PWMR, PIN_S1_PWML, PIN_S1_EN, A7, A1, 1);
LinearActuator flkl("FLKL", PIN_S2_PWMR, PIN_S2_PWML, PIN_S2_EN, A8, A2, 2);
LinearActuator frhy("FRHY", PIN_S3_PWMR, PIN_S3_PWML, PIN_S3_EN, A9, A3, 3);
LinearActuator frhl("FRHL", PIN_S4_PWMR, PIN_S4_PWML, PIN_S4_EN, A10, A4, 4);
LinearActuator frkl("FRKL", PIN_S5_PWMR, PIN_S5_PWML, PIN_S5_EN, A11, A5, 5);
// Left Follower Board
LinearActuator rlhy("RLHY", PIN_S0_PWMR, PIN_S0_PWML, PIN_S0_EN, A6, A0, 0);
LinearActuator rlhl("RLHL", PIN_S1_PWMR, PIN_S1_PWML, PIN_S1_EN, A7, A1, 1);
LinearActuator rlkl("RLKL", PIN_S2_PWMR, PIN_S2_PWML, PIN_S2_EN, A8, A2, 2);
LinearActuator mlhy("MLHY", PIN_S3_PWMR, PIN_S3_PWML, PIN_S3_EN, A9, A3, 3);
LinearActuator mlhl("MLHL", PIN_S4_PWMR, PIN_S4_PWML, PIN_S4_EN, A10, A4, 4);
LinearActuator mlkl("MLKL", PIN_S5_PWMR, PIN_S5_PWML, PIN_S5_EN, A11, A5, 5);
// Right Follower Board
LinearActuator rrhy("RRHY", PIN_S0_PWMR, PIN_S0_PWML, PIN_S0_EN, A6, A0, 0);
LinearActuator rrhl("RRHL", PIN_S1_PWMR, PIN_S1_PWML, PIN_S1_EN, A7, A1, 1);
LinearActuator rrkl("RRKL", PIN_S2_PWMR, PIN_S2_PWML, PIN_S2_EN, A8, A2, 2);
LinearActuator mrhy("MRHY", PIN_S3_PWMR, PIN_S3_PWML, PIN_S3_EN, A9, A3, 3);
LinearActuator mrhl("MRHL", PIN_S4_PWMR, PIN_S4_PWML, PIN_S4_EN, A10, A4, 4);
LinearActuator mrkl("MRKL", PIN_S5_PWMR, PIN_S5_PWML, PIN_S5_EN, A11, A5, 5);

// Role → which 6 actuators this board drives (no mutation)
static const size_t ACT_COUNT = 6;
LinearActuator* ACT_LIST_FRONT[]  = { &flhy, &flhl, &flkl, &frhy, &frhl, &frkl };
LinearActuator* ACT_LIST_LEFT[]   = { &rlhy, &rlhl, &rlkl, &mlhy, &mlhl, &mlkl };  // RL + ML
LinearActuator* ACT_LIST_RIGHT[]  = { &rrhy, &rrhl, &rrkl, &mrhy, &mrhl, &mrkl }; // MR + RR

// Set once after role election.
ActuatorManager* actuatorManager = nullptr;
HardwareSerial* mainSerial = nullptr;  // USB (front) or uplink (left/right)
HardwareSerial* leftSerial = nullptr;  // serial to left board (from front only)
HardwareSerial* rightSerial = nullptr; // serial to right board (from front only)

const LinearActuator::ControlConfig ACTUATOR_CONFIG = {
    5,  // PWM_RAMP_STEP
    10, // RAMP_INTERVAL_MS
    20, // PWM_DEADBAND
    10, // PWM_ERROR_DEADBAND
    2.0 // Kp
};

const size_t CMD_BUF_SIZE = 18;
Command cmdBuf[CMD_BUF_SIZE];

// TELEMETRY_POLL_INTERVAL lives in sensors_config.h and drives the shared
// telemetry/I2C poll cadence.
uint32_t lastTelemetry = 0;

// --- I2C sensor cluster (Milestone 16) — leader board only ---
// The LSM6DSO IMU rides the leader's telemetry tick; followers never touch the bus.
LSM6DSO imu;
bool imuValid = false; // LSM6DSO init succeeded; runtime freshness is per-tick (valid field)
uint8_t imuAddress = 0; // selected only after detection and configuration both succeed

class Lsm6dsoInitBoundary
{
public:
    explicit Lsm6dsoInitBoundary(LSM6DSO &device) : device_(device) {}

    bool begin(uint8_t address)
    {
        return device_.begin(address);
    }

    bool configure()
    {
        return configureLsm6dso(
            device_,
            LSM6DSO_AUTO_INCREMENT,
            LSM6DSO_ACCEL_RANGE_G,
            LSM6DSO_ACCEL_DATA_RATE_HZ,
            LSM6DSO_GYRO_RANGE_DPS,
            LSM6DSO_GYRO_DATA_RATE_HZ,
            LSM6DSO_BLOCK_DATA_UPDATE);
    }

private:
    LSM6DSO &device_;
};

static void logImuInitFailure(ImuInitResult result)
{
    if (result == IMU_INIT_NOT_DETECTED)
    {
        Serial.print(F("IMU CAL: LSM6DSO not detected at 0x"));
        Serial.print(LSM6DSO_I2C_ADDR, HEX);
        Serial.print(F(" or 0x"));
        Serial.print(LSM6DSO_I2C_ADDR_ALT, HEX);
        Serial.println(F("; shipping valid=0."));
        return;
    }

    if (result == IMU_INIT_CONFIGURATION_FAILED)
    {
        Serial.println(F("IMU CAL: LSM6DSO detected but register configuration failed; shipping valid=0."));
        return;
    }

    Serial.println(F("IMU CAL: unexpected initialization result; shipping valid=0."));
}

// INA228 power monitors (Task 3): Pack across the external shunt (total pack
// V/I/P/charge), Midpoint for lower-battery VBUS. Leader-only, on the same bus
// as the LSM6DSO/OLED. Per-device validity so one missing board doesn't block it.
Adafruit_INA228 inaPack;
Adafruit_INA228 inaMid;
bool packValid = false; // Pack (0x40) init succeeded
bool midValid = false;  // Midpoint (0x41) init succeeded

// OLED status render (Task 2/3): the krab UI on the 1.3" panel, leader-only,
// on the same Qwiic chain. Ported 1:1 from firmware/oled_sim/krab.py; driven by
// live telemetry (role, IMU roll/pitch, INA228 pack V + battery bars). A drawn
// frame is a full erase()+redraw()+display() (~120 ms full-frame I2C); the
// library cannot diff across an erase, so oledRenderKrab skips the whole draw
// when the state is unchanged.
Qwiic1in3OLED oled;
bool oledValid = false;
unsigned long lastOledDraw = 0;
// Latest body-frame accel (m/s^2) cached by imuAppendTelemetry for the OLED's
// roll/pitch — avoids a second getSensorData() on the render tick.
float oledAccel[3] = {0, 0, 0};
bool oledAccelFresh = false;

// Gyro/accel bias in the RAW sensor frame (deg/s, g), captured at boot while
// stationary and persisted at EEPROM_IMU_CAL_ADDR. Stored pre-transform so a
// later change to IMU_AXIS_SRC/SIGN doesn't invalidate saved calibration.
struct ImuCalData
{
    uint8_t magic;
    uint8_t schema;
    float gyroBiasDps[3];
    // accelBiasG is the per-axis accelerometer offset, in g, in the raw
    // sensor frame. No code writes it yet: boot calibration captures only the
    // gyro bias, so accelBiasG holds zeros on every board today, and
    // subtracting zero changes nothing. imuAppendTelemetry() nevertheless
    // subtracts it on every tick, on purpose: when an accel-offset capture
    // routine is added later, that change is a new writer function only — the
    // telemetry wire format, the EEPROM byte layout, and the schema version
    // all stay exactly as they are. The field exists now solely to keep the
    // stored layout stable.
    float accelBiasG[3];
};
ImuCalData imuCal = {};

// INA228 calibration (Task 3, AC 3i): per-board VBUS offset trims so the two
// monitors agree with a reference DMM, plus a Pack shunt-cal fine trim on the
// current channel. Captured at the bench against a known voltage/current via the
// serial power-sensor calibration command (handleCalibrationCommand below;
// procedure in
// docs/M16-INA228-CALIBRATION.md) and persisted at EEPROM_INA_CAL_ADDR with the
// same torn-write-safe magic scheme as the IMU block. A board with no valid block
// runs identity trims (gain 1, offset 0, shunt 1) — the read is uncorrected,
// never wrong. Layout pinned to EEPROM_INA_CAL_SIZE.
static_assert(sizeof(PowerCalibrationData) == EEPROM_INA_CAL_SIZE,
              "update EEPROM_INA_CAL_SIZE in sensors_config.h");
static const PowerCalibrationStorageRules POWER_CALIBRATION_STORAGE_RULES = {
    EEPROM_INA_CAL_MAGIC,
    EEPROM_INA_CAL_SCHEMA,
    INA228_CAL_MAX_VOFFSET_V,
    INA228_CAL_MIN_GAIN,
    INA228_CAL_MAX_GAIN};
PowerCalibrationData inaCal = identityPowerCalibration();

static bool imuCalPlausible();

static void imuCaptureGyroBias()
{
    float sum[3] = {0, 0, 0};
    float lo[3], hi[3];
    int good = 0;
    for (int i = 0; i < IMU_CAL_SAMPLES; i++)
    {
        // LSM6DSO float reads carry no per-sample status (unlike the BMI270's
        // getSensorData()), so every loop iteration yields a sample. readFloatGyroX
        // returns deg/s, matching gyroBiasDps's units, so the averaging math below
        // is byte-for-byte the same as under the BMI270.
        {
            float g[3] = {imu.readFloatGyroX(), imu.readFloatGyroY(), imu.readFloatGyroZ()};
            for (int a = 0; a < 3; a++)
            {
                sum[a] += g[a];
                if (good == 0 || g[a] < lo[a]) lo[a] = g[a];
                if (good == 0 || g[a] > hi[a]) hi[a] = g[a];
            }
            good++;
        }
        delay(IMU_CAL_SAMPLE_DELAY_MS);
    }
    if (good < IMU_CAL_SAMPLES / 2)
    {
        Serial.println(F("IMU CAL: too few samples; bias left at zero, not saved."));
        return;
    }
    // Not stationary: leave EEPROM unwritten so the capture retries next boot.
    for (int a = 0; a < 3; a++)
    {
        if (hi[a] - lo[a] > IMU_CAL_MAX_SPREAD_DPS)
        {
            Serial.println(F("IMU CAL: motion detected; bias left at zero, not saved."));
            return;
        }
    }
    for (int a = 0; a < 3; a++)
        imuCal.gyroBiasDps[a] = sum[a] / good;
    // Two-phase write: put() streams bytes from offset 0, so a power loss
    // mid-write (~86 ms) would otherwise persist a valid magic over garbage
    // floats. Write the block with invalid magic first, then flip the real
    // magic last — a torn write always fails validation and recaptures.
    imuCal.magic = EEPROM_IMU_CAL_INVALID_MAGIC;
    imuCal.schema = EEPROM_IMU_CAL_SCHEMA;
    EEPROM.put(EEPROM_IMU_CAL_ADDR, imuCal);
    imuCal.magic = EEPROM_IMU_CAL_MAGIC;
    EEPROM.update(EEPROM_IMU_CAL_ADDR, EEPROM_IMU_CAL_MAGIC);
    EEPROM.get(EEPROM_IMU_CAL_ADDR, imuCal);
    if (!imuCalPlausible())
    {
        imuCal = ImuCalData{};
        Serial.println(F("IMU CAL: EEPROM verification failed; bias left at zero, retrying next boot."));
        return;
    }
    Serial.println("IMU CAL: gyro bias captured and saved to EEPROM.");
}

// Stored cal must survive the magic check AND look like calibration: all six
// floats finite, gyro bias within IMU_CAL_MAX_BIAS_DPS. Any failure is treated
// exactly like a missing block (fresh capture).
static bool imuCalPlausible()
{
    if (imuCal.magic != EEPROM_IMU_CAL_MAGIC || imuCal.schema != EEPROM_IMU_CAL_SCHEMA)
        return false;
    for (int a = 0; a < 3; a++)
    {
        if (!isfinite(imuCal.gyroBiasDps[a]) || fabs(imuCal.gyroBiasDps[a]) > IMU_CAL_MAX_BIAS_DPS)
            return false;
        if (!isfinite(imuCal.accelBiasG[a]))
            return false;
    }
    return true;
}

// Blocks the leader ~1.2 s per boot (~2.9 s when bias capture runs on an
// uncalibrated boot). Safe: the 3 s role election precedes it, the SDK sleeps
// 5 s post-connect, and follower RX overflow during the block is dropped by
// the prefix filter. Called only from setup(): runtime recovery deliberately
// does NOT re-run this in-loop (the ~1.2 s block would stall the live actuator
// control loop, AC 1b), so allowBiasCapture is true on the one boot-time call.
static void imuSetup(bool allowBiasCapture)
{
    Wire.begin();
    Wire.setClock(I2C_BUS_CLOCK_HZ);
    Wire.setWireTimeout(I2C_WIRE_TIMEOUT_US, true);  // see sensors_config.h

    uint8_t selectedAddress = 0;
    Lsm6dsoInitBoundary imuDevice(imu);
    ImuInitResult initResult = initializeImu(
        imuDevice,
        LSM6DSO_I2C_ADDR,
        LSM6DSO_I2C_ADDR_ALT,
        selectedAddress);
    // Derive validity from the complete result in one place. This remains
    // correct if setup is later reused as a retry after a previously healthy
    // sensor: either failure class actively clears the old valid state.
    imuValid = initResult == IMU_INIT_OK;
    if (!imuValid)
    {
        imuAddress = 0;
        logImuInitFailure(initResult);
        return;
    }
    imuAddress = selectedAddress;
    Serial.print("IMU CAL: LSM6DSO online at 0x");
    Serial.println(imuAddress, HEX);

    EEPROM.get(EEPROM_IMU_CAL_ADDR, imuCal);
    if (imuCalPlausible())
    {
        Serial.println(F("IMU CAL: loaded from EEPROM."));
    }
    else
    {
        imuCal = ImuCalData{};
        if (allowBiasCapture)
            imuCaptureGyroBias();
    }
}

// Runtime IMU health. An LSM6DSO power-on-reset (3.3 V Dupont run + vibration)
// leaves the part powered down (ODR=0): it still ACKs reads, but the data
// registers read exactly 0x0000, so the float reads return zeros. After
// IMU_REINIT_AFTER_BAD_TICKS consecutive bad ticks imuValid is dropped so the
// wire ships valid=0 (the host's signal that the sensor is wedged). The blocking
// config re-upload (imuSetup, ~1.2 s) is intentionally NOT run in-loop — it would
// stall the live actuator control loop (AC 1b) — so a wedged sensor recovers only
// on the next reboot. Runs SILENTLY: this is reached mid-telemetry-line (from
// imuAppendTelemetry, before the ;IMU segment), so it must never Serial.print —
// a stray newline would splice the open line, as the INA recovery path also avoids.
static uint8_t imuBadTicks = 0;
static unsigned long imuLastReinit = 0;

static void imuMaybeRecover()
{
    if (imuBadTicks < 255) imuBadTicks++;
    if (imuBadTicks < IMU_REINIT_AFTER_BAD_TICKS) return;
    if (millis() - imuLastReinit < IMU_REINIT_INTERVAL_MS) return;
    imuLastReinit = millis();
    imuValid = false;   // ship valid=0 until a reboot re-uploads the config
    imuBadTicks = 0;
}

// Append ";IMU ax ay az gx gy gz temp valid" (m/s^2, rad/s, C) to the open
// telemetry line. Keep in sync with firmware/interfaces/joint_telemetry.py.
static void imuAppendTelemetry(Print& out)
{
    float a[3] = {0, 0, 0}, g[3] = {0, 0, 0}, tempC = 0;
    bool fresh = false;
    if (imuValid)
    {
        Lsm6dsoOutputSample sample = {};
        const bool readOk = readLsm6dsoOutputSample(Wire, imuAddress, sample);
        // A configured accelerometer always sees gravity; all six raw axes
        // reading exactly zero is a browned-out sensor in suspend, not data.
        // Preferred over the STATUS drdy bits: those clear on data-read and go
        // low on a healthy sensor whenever the tick outpaces the ODR, which
        // would ship spurious valid=0 to the locomotion model.
        bool allZero = sample.accel[0] == 0 && sample.accel[1] == 0 && sample.accel[2] == 0 &&
                       sample.gyro[0] == 0 && sample.gyro[1] == 0 && sample.gyro[2] == 0;
        if (readOk && !allZero)
        {
            float rawA[3], rawG[3];
            for (int i = 0; i < 3; i++)
            {
                rawA[i] = sample.accel[i] * LSM6DSO_ACCEL_G_PER_LSB;
                rawG[i] = sample.gyro[i] * LSM6DSO_GYRO_DPS_PER_LSB;
            }
            for (int i = 0; i < 3; i++)
            {
                a[i] = IMU_AXIS_SIGN[i] * (rawA[IMU_AXIS_SRC[i]] - imuCal.accelBiasG[IMU_AXIS_SRC[i]]) * IMU_ACCEL_G_TO_MS2;
                g[i] = IMU_AXIS_SIGN[i] * (rawG[IMU_AXIS_SRC[i]] - imuCal.gyroBiasDps[IMU_AXIS_SRC[i]]) * IMU_GYRO_DEG_TO_RAD;
            }
            tempC = sample.temperature * LSM6DSO_TEMP_C_PER_LSB +
                    LSM6DSO_TEMP_OFFSET_C;
            fresh = true;
            oledAccel[0] = a[0]; oledAccel[1] = a[1]; oledAccel[2] = a[2];  // for OLED roll/pitch
            oledAccelFresh = true;
        }
    }
    if (fresh)
        imuBadTicks = 0;
    else
        imuMaybeRecover();
    out.print(TELEMETRY_SEGMENT_DELIMITER);
    out.print(IMU_TELEMETRY_TAG);
    out.print(TELEMETRY_FIELD_DELIMITER);
    for (int i = 0; i < 3; i++) { out.print(a[i], 3); out.print(TELEMETRY_FIELD_DELIMITER); }
    for (int i = 0; i < 3; i++) { out.print(g[i], 4); out.print(TELEMETRY_FIELD_DELIMITER); }
    out.print(tempC, 1);
    out.print(TELEMETRY_FIELD_DELIMITER);
    out.print(fresh ? 1 : 0);
}

// Stored INA cal must survive the magic check AND look like calibration: all
// three floats finite, both offsets bounded, and the shunt scale near unity.
// Bring up both INA228 monitors on the shared I2C bus (already begun by imuSetup).
// Per-device: one missing board must not block the other. Pack gets the external
// shunt calibration; Midpoint is VBUS-only (current channel unused). The Pack
// charge accumulator is zeroed so pack_charge counts from this boot.
static void inaSetup()
{
    packValid = startPackIna(
        inaPack, INA228_PACK_I2C_ADDR, &Wire, PackInaStart::Boot);
    if (packValid)
    {
        Serial.println(F("INA: Pack (0x40) online, setShunt(0.000375, 200)."));
    }
    else
        Serial.println(F("INA: Pack (0x40) init FAILED; BATT segment suppressed."));

    midValid = inaMid.begin(INA228_MID_I2C_ADDR, &Wire);
    Serial.println(midValid ? F("INA: Midpoint (0x41) online.")
                            : F("INA: Midpoint (0x41) init FAILED."));

    if (loadPowerCalibration(
            EEPROM,
            EEPROM_INA_CAL_ADDR,
            POWER_CALIBRATION_STORAGE_RULES,
            inaCal))
        Serial.println(F("POWER CAL: loaded from EEPROM."));
    else
    {
        Serial.println(F("POWER CAL: none/invalid; running identity trims."));
    }
}

// Runtime INA228 recovery: a wedged/browned-out monitor is re-begun on an interval
// so a transient (Qwiic knock, brownout) self-heals. PER-DEVICE and QUIET — re-inits
// only the failed monitor, with NO Serial output (never splices boot prints into the
// open telemetry line) and NO EEPROM cal reload, so a healthy sibling's charge
// accumulator is never disturbed. Reuses the IMU reinit cadence (generic stuck-I2C
// retry). Separate counters so a good Pack tick can't mask a wedged Midpoint.
static uint8_t inaPackBadTicks = 0, inaMidBadTicks = 0;
static unsigned long inaPackLastReinit = 0, inaMidLastReinit = 0;

static void inaRecoverPack()
{
    if (inaPackBadTicks < 255) inaPackBadTicks++;
    if (inaPackBadTicks < IMU_REINIT_AFTER_BAD_TICKS) return;
    if (millis() - inaPackLastReinit < IMU_REINIT_INTERVAL_MS) return;
    inaPackLastReinit = millis();
    // A mid-run re-begin skips the device reset so a still-powered INA228 retains
    // its CHARGE accumulator. A physical INA228 brownout has already cleared that
    // hardware state; recovery cannot reconstruct the lost interval.
    packValid = startPackIna(
        inaPack, INA228_PACK_I2C_ADDR, &Wire, PackInaStart::Recovery);
    inaPackBadTicks = 0;
}

static void inaRecoverMid()
{
    if (inaMidBadTicks < 255) inaMidBadTicks++;
    if (inaMidBadTicks < IMU_REINIT_AFTER_BAD_TICKS) return;
    if (millis() - inaMidLastReinit < IMU_REINIT_INTERVAL_MS) return;
    inaMidLastReinit = millis();
    midValid = inaMid.begin(INA228_MID_I2C_ADDR, &Wire);
    inaMidBadTicks = 0;
}

// --- INA228 bench calibration capture (AC 3i) ---
// VBUS calibration needs an EXTERNAL known reference (a DMM on the live pack), so
// unlike imuCaptureGyroBias it cannot self-run at boot; the operator triggers it
// from the bench with the serial power-calibration command. Full procedure lives in
// docs/M16-INA228-CALIBRATION.md. Every write reuses imuCaptureGyroBias's
// torn-write-safe scheme (inaPersistCal): stream the block with magic=0x00 first,
// then flip the real magic byte in last, so a power loss mid-write always fails
// the magic check on reload and falls back to identity trims. Every path that
// could produce a bad number bails BEFORE writing, so a mistyped bench reference
// leaves the prior (or identity) calibration untouched.

static void inaPersistCal()
{
    persistPowerCalibration(
        EEPROM,
        EEPROM_INA_CAL_ADDR,
        POWER_CALIBRATION_STORAGE_RULES,
        inaCal);
}

static void printPowerCalibration()
{
    // F() keeps these literals in flash, not SRAM (this bench-only help/status
    // text would otherwise cost ~1 KB of the Mega's 8 KB RAM).
    Serial.print(F("POWER CAL: packVoltageOffset=")); Serial.print(inaCal.packVoltageOffset, 4);
    Serial.print(F(" midpointVoltageOffset="));      Serial.print(inaCal.midpointVoltageOffset, 4);
    Serial.print(F(" packShuntCal="));       Serial.println(inaCal.packShuntCal, 5);
}

static void printPowerCalibrationUsage()
{
    Serial.println(F("POWER CAL usage (leader bench only):"));
    Serial.println(F("  C PWR_SENSE VOLTAGE <packReferenceVolts> <midpointReferenceVolts>"));
    Serial.println(F("  C PWR_SENSE CURRENT <knownAmps>"));
    Serial.println(F("  C PWR_SENSE SHOW"));
    Serial.println(F("  C PWR_SENSE ?"));
}

// Parse and dispatch one calibration command line (the leading 'C' already
// consumed). Bare C retains the existing whole-controller actuator calibration;
// C ACTUATOR is its explicit equivalent. C PWR_SENSE is leader-only and is
// never forwarded to follower boards.
static void handleCalibrationCommand(const String& line)
{
    int idx = 0;
    const int len = line.length();
    String tokenStorage[5];
    const char* tokens[5];
    size_t tokenCount = 0;
    while (tokenCount < 5)
    {
        tokenStorage[tokenCount] = nextTok(line, idx, len);
        if (tokenStorage[tokenCount].length() == 0)
            break;
        tokens[tokenCount] = tokenStorage[tokenCount].c_str();
        ++tokenCount;
    }

    if (isActuatorCalibrationCommand(tokenCount, tokens))
    {
        actuatorManager->startAutoCalibration();
        if (leftSerial) leftSerial->println(CALIBRATION_COMMAND_PREFIX);
        if (rightSerial) rightSerial->println(CALIBRATION_COMMAND_PREFIX);
        return;
    }

    PowerCalibrationCommand command = {
        PowerCalibrationOperation::Invalid, 0.0f, 0.0f};
    if (!parsePowerCalibrationCommand(tokenCount, tokens, command))
    {
        Serial.println(F("POWER CAL: invalid command; no write."));
        printPowerCalibrationUsage();
        return;
    }

    if (command.operation == PowerCalibrationOperation::Show ||
        command.operation == PowerCalibrationOperation::Help)
    {
        if (command.operation == PowerCalibrationOperation::Show)
            printPowerCalibration();
        else
            printPowerCalibrationUsage();
        return;
    }

    // Every capture reads the Pack monitor; voltage calibration also reads the
    // Midpoint. Gate each on exactly what it touches so a Pack-only shunt trim
    // still works when the Midpoint board is absent.
    if (!packValid)
    {
        Serial.println(F("POWER CAL: Pack monitor offline; aborting (no write)."));
        return;
    }

    if (command.operation == PowerCalibrationOperation::Voltage)
    {
        if (!midValid)
        {
            Serial.println(F("POWER CAL: Midpoint offline; voltage calibration needs both; aborting (no write)."));
            return;
        }
        VoltageOffsets offsets = {
            Volts(inaCal.packVoltageOffset),
            Volts(inaCal.midpointVoltageOffset)};
        const VoltageCalibrationLimits limits = {
            Volts(INA228_CAL_PACK_REF_MAX_V),
            Volts(INA228_CAL_MID_REF_MAX_V),
            Volts(INA228_CAL_MAX_VOFFSET_V)};
        if (!captureVoltageOffsets(
                inaPack,
                inaMid,
                Volts(command.firstReference),
                Volts(command.secondReference),
                limits,
                offsets))
        {
            Serial.println(F("POWER CAL: invalid reference, reading, or solved offset; aborting (no write)."));
            return;
        }

        inaCal.packVoltageOffset = offsets.packVoltageOffset.value();
        inaCal.midpointVoltageOffset =
            offsets.midpointVoltageOffset.value();
        inaPersistCal();
        Serial.println(F("POWER CAL: voltage offsets saved and applied."));
        printPowerCalibration();
        return;
    }

    if (command.operation == PowerCalibrationOperation::Current)
    {
        // Shunt current trim: operator forces a known current through the pack
        // shunt (electronic load / bench supply), signed to match the sensor.
        const Amps knownCurrent(command.firstReference);
        const Amps measuredCurrent =
            toAmps(MilliAmps(inaPack.readCurrent()));
        float trim = inaCal.packShuntCal;
        if (!calculateShuntTrim(
                knownCurrent,
                measuredCurrent,
                Amps(INA228_CAL_MIN_SHUNT_TRIM_A),
                INA228_CAL_MIN_GAIN,
                INA228_CAL_MAX_GAIN,
                trim))
        {
            Serial.println(F("POWER CAL: invalid current pair or solved shunt trim; aborting (no write)."));
            return;
        }
        inaCal.packShuntCal = trim;
        inaPersistCal();
        Serial.println(F("POWER CAL: Pack current calibration saved and applied."));
        printPowerCalibration();
        return;
    }
}

// Append ";BATT pack_v pack_i pack_w pack_charge batt_a batt_b divergence
// power_state" (V, A signed, W, C, V, V, 0/1, enum) to the open leader line.
// Emitted only when BOTH monitors are up and the reads produce two plausible
// battery voltages. The wire frame is atomic (the parser needs all six values
// finite), so a down monitor omits the whole segment rather than fabricating a
// balanced split. Keep in sync with joint_telemetry.py.
static void battAppendTelemetry(Print& out)
{
    // Pack is the essential monitor: no pack read -> no frame. Read + range-check;
    // an implausible read marks the Pack down for a quiet per-device re-begin.
    // Library units are mixed (verified in the ina228_read bench sketch):
    // readBusVoltage() V, readCurrent() mA, readPower() mW, readCharge() C.
    const float packV = packValid
        ? readCorrectedInaBusVoltage(
            inaPack, Volts(inaCal.packVoltageOffset)).value()
        : NAN;
    if (!packValid || !batteryPackVoltageIsValid(packV))
    {
        packValid = false;
        inaRecoverPack();
        return;                         // nothing trustworthy to ship
    }
    inaPackBadTicks = 0;                 // a good pack read clears its counter

    // A complete BATT frame claims two measured battery voltages. If the
    // Midpoint monitor is missing or the pack/midpoint pair cannot describe two
    // plausible batteries, omit the atomic frame and recover the Midpoint
    // independently. Never turn missing data into a synthetic balanced pack.
    const float midpointV = midValid
        ? readCorrectedInaBusVoltage(
            inaMid, Volts(inaCal.midpointVoltageOffset)).value()
        : NAN;
    BatterySplit split;
    if (!midValid ||
        !calculateBatterySplit(
            packV, midpointV, INA228_DIVERGENCE_THRESHOLD, split))
    {
        midValid = false;
        inaRecoverMid();
        return;
    }
    inaMidBadTicks = 0;

    const Amps packI = applyShuntTrim(
        toAmps(MilliAmps(inaPack.readCurrent())), inaCal.packShuntCal);
    const Watts packW = applyShuntTrim(
        toWatts(MilliWatts(inaPack.readPower())), inaCal.packShuntCal);
    const Coulombs packQ = applyShuntTrim(
        Coulombs(inaPack.readCharge()), inaCal.packShuntCal);
    uint8_t powerState = BATTERY_POWER_NORMAL;

    const BatteryTelemetryFrame frame = {
        Volts(packV),
        packI,
        packW,
        packQ,
        Volts(split.batteryA),
        Volts(split.batteryB),
        split.diverged,
        powerState
    };
    appendBatteryTelemetry(out, frame);
}

// ===========================================================================
// OLED krab status render — 1:1 firmware port of firmware/oled_sim/krab.py
// (RENDER_SPEC.md §5): same geometry + draw-call order, integer voltage format
// (no %f), signed int for the leg math, one display() flush. SparkFun's driver
// transfers only each page's dirty x-range. Because erase()+redraw can dirty
// most of the screen, the shared bus runs at 400 kHz so even the conservative
// worst-case wire-time estimate remains below the 50 ms loop budget. To keep
// unchanged frames off the wire entirely, oledRenderKrab also caches the last
// rendered OledKrabState and skips erase()+redraw()+display().
// Keep constants in lockstep with krab.py.
// ===========================================================================
#define OLED_REDRAW_INTERVAL_MS 250      // 4 Hz status refresh; well off the 50 ms tick

static const int OLED_GLYPH = 9;
static const int OLED_BAND_H = OLED_GLYPH + 1;                        // 10
static const int OLED_BODY_W = 32, OLED_BODY_H = OLED_BAND_H * 3 + 1; // 32 x 31
static const int OLED_BODY_X = (128 - OLED_BODY_W) / 2;              // 48
static const int OLED_BODY_Y = 22;
static const int OLED_TBAR_Y = OLED_BODY_Y + 2 * OLED_BAND_H;        // 42
static const int OLED_STEM_X = OLED_BODY_X + OLED_BODY_W / 2;        // 64
static const int OLED_LEG_BAND[6] = {2, 2, 1, 1, 0, 0};
static const int OLED_BAT_W = 18, OLED_BAT_H = 7, OLED_BAT_HGAP = 4;
static const int OLED_BAT_X = 2, OLED_BAT_Y = 11;
static const int OLED_BAT_NUB_W = 2, OLED_BAT_NUB_H = 3;
static const int OLED_BAT_PITCH = OLED_BAT_W + OLED_BAT_NUB_W + OLED_BAT_HGAP;
static void oledGlyph(int cx, int cy, OledGlyph st) {
  drawOledActuatorGlyph(oled, cx, cy, st, OLED_GLYPH);
}

// Live glyph for one actuator: DISC if not physically attached, else EXTEND /
// RETRACT / HOLD from the ramped applied PWM (currentPwm; + = extend, - =
// retract per driveActuator()). OLED_PWM_MOVE_MIN is sourced from
// ACTUATOR_CONFIG.pwmDeadband (single source of truth) — driveActuator()
// de-energizes only when abs(pwm) < pwmDeadband, so at |pwm| == deadband the
// motor IS driven; the comparisons are inclusive so the glyph shows motion at
// exactly that boundary, matching driveActuator() rather than lagging by one.
static const int OLED_PWM_MOVE_MIN = ACTUATOR_CONFIG.pwmDeadband;
static OledGlyph glyphForActuator(const LinearActuator* a) {
  return actuatorGlyph(a->isConnected(), a->currentPwm, OLED_PWM_MOVE_MIN);
}

// Render cache for oledRenderKrab's skip-when-unchanged (AC 2h). File-scope so a
// path that writes the panel directly (a Task-4 low-power splash / panel clear)
// can force the next krab frame to fully redraw via oledInvalidateKrabCache() —
// otherwise a resume to the same pre-sleep state would match the cache and leave
// a blank panel.
static OledKrabState oledKrabCached;
static bool oledKrabCacheValid = false;
static inline void oledInvalidateKrabCache() { oledKrabCacheValid = false; }

static void oledRenderKrab(const OledKrabState &s) {
  // Skip-when-unchanged: even a dirty-page transfer is wasted bus time when the
  // rendered state is identical.
  // Cache the last-rendered state and bail before touching I2C when it matches.
  if (oledKrabCacheValid && s == oledKrabCached) return;
  oledKrabCached = s;
  oledKrabCacheValid = true;

  oled.erase();
  oled.setFont(QW_FONT_5X7);
  int dv = (int)lround(s.packVoltage * 10.0f);
  int roll = s.roll < -99 ? -99 : (s.roll > 99 ? 99 : s.roll);
  int pitch = s.pitch < -99 ? -99 : (s.pitch > 99 ? 99 : s.pitch);
  char top[24];
  snprintf(top, sizeof(top), "%s %+03d/%+03d %d.%dV", s.role, roll, pitch, dv / 10, dv % 10);
  oled.text(0, 0, top);
  oled.line(0, 9, 127, 9);

  int fill_h = OLED_BAT_H - 2;
  int nub_dy = (OLED_BAT_H - OLED_BAT_NUB_H) / 2;
  for (int j = 0; j < 2; j++) {
    int bx = OLED_BAT_X + j * OLED_BAT_PITCH;
    oled.rectangle(bx, OLED_BAT_Y, OLED_BAT_W, OLED_BAT_H);
    oled.rectangleFill(bx + OLED_BAT_W, OLED_BAT_Y + nub_dy, OLED_BAT_NUB_W, OLED_BAT_NUB_H);
    float frac = s.batteryLevels[j] < 0
        ? 0
        : (s.batteryLevels[j] > 1 ? 1 : s.batteryLevels[j]);
    int fw = (int)lround((OLED_BAT_W - 2) * frac);
    if (fw > 0) oled.rectangleFill(bx + 1, OLED_BAT_Y + 1, fw, fill_h);
  }

  oled.rectangle(OLED_BODY_X, OLED_BODY_Y, OLED_BODY_W, OLED_BODY_H);
  if (s.left)  oled.rectangleFill(OLED_BODY_X + 1, OLED_BODY_Y + 1, OLED_STEM_X - OLED_BODY_X - 1, OLED_TBAR_Y - OLED_BODY_Y - 1);
  if (s.right) oled.rectangleFill(OLED_STEM_X, OLED_BODY_Y + 1, OLED_BODY_X + OLED_BODY_W - 1 - OLED_STEM_X, OLED_TBAR_Y - OLED_BODY_Y - 1);
  if (s.front) oled.rectangleFill(OLED_BODY_X + 1, OLED_TBAR_Y, OLED_BODY_W - 2, OLED_BODY_Y + OLED_BODY_H - 1 - OLED_TBAR_Y);

  int r = OLED_GLYPH / 2;
  int GAP = 5;
  int step = 2 * r + GAP;
  for (int i = 0; i < 6; i++) {
    int by = OLED_BODY_Y + OLED_LEG_BAND[i] * OLED_BAND_H + OLED_BAND_H / 2;
    int sign = (i % 2 == 0) ? -1 : 1;
    int edge = (sign < 0) ? OLED_BODY_X : OLED_BODY_X + OLED_BODY_W;
    int px = edge, py = by;
    for (int j = 0; j < 3; j++) {
      int cx = edge + sign * (r + GAP + j * step);
      int gy = by;
      oled.line(px, py, cx - sign * r, gy);
      oledGlyph(cx, gy, s.legs[i][j]);
      px = cx + sign * r; py = gy;
    }
  }

  int fcx = OLED_BODY_X + OLED_BODY_W / 2;
  int fy = OLED_BODY_Y + OLED_BODY_H - 1;
  int exs[2] = {fcx - 6, fcx + 6};
  for (int k = 0; k < 2; k++) {
    int ex = exs[k];
    oled.line(ex, fy + 1, ex, fy + 2);
    int ey = fy + 3;
    oled.line(ex - 1, ey, ex + 1, ey);
    oled.line(ex - 1, ey + 2, ex + 1, ey + 2);
    oled.line(ex - 1, ey, ex - 1, ey + 2);
    oled.line(ex + 1, ey, ex + 1, ey + 2);
  }
  oled.pixel(fcx - 2, fy + 4); oled.pixel(fcx + 2, fy + 4);
  oled.line(fcx - 1, fy + 5, fcx + 1, fy + 5);

  oled.display();
}

// Follower presence tracks only complete telemetry carrying the expected
// role-elected prefix. Diagnostics and command/version replies are forwarded
// normally but cannot make a telemetry-silent controller appear active.
// Followers emit telemetry every TELEMETRY_INTERVAL_MS (50 ms / 20 Hz), so
// 500 ms absorbs ~10 dropped ticks without flicker while staying responsive
// at the 250 ms OLED redraw.
static const uint32_t OLED_PRESENCE_MS = 500;
static ControllerTelemetryFreshness followerLeftFreshness = {false, 0};
static ControllerTelemetryFreshness followerRightFreshness = {false, 0};
static OledGlyph followerLeftGlyphs[6] = {
  OG_DISC, OG_DISC, OG_DISC, OG_DISC, OG_DISC, OG_DISC
};
static OledGlyph followerRightGlyphs[6] = {
  OG_DISC, OG_DISC, OG_DISC, OG_DISC, OG_DISC, OG_DISC
};
static bool followerLeftConnected[6] = {
  false, false, false, false, false, false
};
static bool followerRightConnected[6] = {
  false, false, false, false, false, false
};

// Build the state from LIVE telemetry and draw. role from election; roll/pitch
// from the cached IMU accel; pack V + battery bars are Task 3 placeholders (0.0
// until the power monitor lands). Body presence is live (FRONT always here;
// LEFT/RIGHT from follower-link recency). Every Mega contributes the same six
// actuator states: the display owner's come directly from its actuator objects,
// while LEFT/RIGHT are decoded from those Megas' forwarded telemetry.
static void oledRenderLive() {
  OledKrabState s;

  // Role election owns controller identity; freshness below only determines
  // whether an assigned follower slot is presently active or missing.
  ControllerSlotLinks slots = controllerSlotLinks(
      currentRole, leftSerial != NULL, rightSerial != NULL);
  unsigned long now = millis();
  s.front = slots.frontLocal;
  s.left = controllerTelemetryIsFresh(
      slots.leftAssigned, followerLeftFreshness, now, OLED_PRESENCE_MS);
  s.right = controllerTelemetryIsFresh(
      slots.rightAssigned, followerRightFreshness, now, OLED_PRESENCE_MS);

  OledGlyph localGlyphs[6];
  for (int actuator = 0; actuator < 6; ++actuator)
    localGlyphs[actuator] = glyphForActuator(ACT_LIST_FRONT[actuator]);

  const OledGlyph missingGlyphs[6] = {
    OG_DISC, OG_DISC, OG_DISC, OG_DISC, OG_DISC, OG_DISC
  };
  setControllerLegGlyphs(s.legs, 0, 1, localGlyphs); // FRONT: FL, FR
  setControllerLegGlyphs(
      s.legs, 4, 2, s.left ? followerLeftGlyphs : missingGlyphs); // LEFT: RL, ML
  setControllerLegGlyphs(
      s.legs, 5, 3, s.right ? followerRightGlyphs : missingGlyphs); // RIGHT: RR, MR

  s.role = roleName(currentRole);

  if (oledAccelFresh) {                     // roll about body X, pitch about body Y
    float ax = oledAccel[0], ay = oledAccel[1], az = oledAccel[2];
    s.roll = (int)lround(atan2(ay, az) * 57.2957795f);
    s.pitch = (int)lround(atan2(-ax, sqrt(ay * ay + az * az)) * 57.2957795f);
  } else {
    s.roll = 0; s.pitch = 0;
  }

  float packV = 0.0f;
  if (packValid)
    packV = readCorrectedInaBusVoltage(
        inaPack, Volts(inaCal.packVoltageOffset)).value();
  s.packVoltage = packV;
  const float midpointV = midValid
      ? readCorrectedInaBusVoltage(
          inaMid, Volts(inaCal.midpointVoltageOffset)).value()
      : NAN;
  BatterySplit split;
  if (packValid && midValid &&
      calculateBatterySplit(
          packV, midpointV, INA228_DIVERGENCE_THRESHOLD, split)) {
    s.batteryLevels[0] =
        BatteryLevel::fromVoltage(Volts(split.batteryA)).value();
    s.batteryLevels[1] =
        BatteryLevel::fromVoltage(Volts(split.batteryB)).value();
  } else {
    // A missing Midpoint cannot truthfully produce two battery bars. Keep both
    // at the unavailable baseline instead of inventing a balanced split.
    s.batteryLevels[0] = 0.0f;
    s.batteryLevels[1] = 0.0f;
  }

  oledRenderKrab(s);
}

// One line = "ROLE; " + ACT_COUNT segments; allow ~55 chars per segment to avoid truncation.
// This buffer only holds *forwarded follower* lines, which never carry IMU/BATT
// segments — the leader's own line (where sensor segments are appended) is
// printed straight to mainSerial and never buffered here.
//
// Per-tick upstream byte budget (leader USB link, 8N1): BAUD_RATE/10 bytes/s
// * TELEMETRY_POLL_INTERVAL = 1250 B per 50 ms tick at 250000 baud. Each tick
// carries three lines: the leader's own ("FRONT; " + 6 joint segments + IMU
// segment [+ BATT in Task 3] + CRLF, 207-341 B derived per-field: each joint
// segment 24-44 B (pos 6, pot/current 4, PWM 3, uint32 hall 10 worst); IMU
// segment 49-63 B) plus two forwarded follower lines (158-278 B each — same
// derivation minus the IMU segment). Bench-measured idle (2026-07-06):
// leader line 229 B + 2 forwarded lines at 180 B = 589 B/tick = 47%
// utilization (at 115200 the budget was 576 B, so 589 B = 102% — the M16
// line no longer fit). The Task 3 BATT segment (battAppendTelemetry) adds
// ~50-70 B to the leader line (";BATT " + 6 floats + flag + state), taking the
// leader line to ~280-300 B and the tick to ~53% — comfortably within budget.
#define TELEMETRY_LINE_MAX (8 + (ACT_COUNT * 55))

static char leftPartial[TELEMETRY_LINE_MAX];
static char rightPartial[TELEMETRY_LINE_MAX];
static size_t leftPartialPos = 0;
static size_t rightPartialPos = 0;

// Forward only complete lines (up to and including \n) from follower serial to mainSerial.
void forwardFullLines(
    HardwareSerial* from,
    HardwareSerial* to,
    char* partial,
    size_t cap,
    size_t* partialPos,
    const char* expectedRoleLabel,
    ControllerTelemetryFreshness* freshness,
    OledGlyph (*glyphs)[6],
    bool (*connected)[6])
{
    if (!from || !to || !partial || !partialPos) return;
    while (from->available())
    {
        char c = (char)from->read();
        if (c == '\n')
        {
            partial[*partialPos] = '\0';
            if (*partialPos > 0)
            {
                to->println(partial);
                if (isExpectedControllerTelemetry(partial, expectedRoleLabel))
                {
                    if (freshness)
                        noteControllerTelemetry(*freshness, millis());
                    if (glyphs && connected)
                        parseControllerActuatorStates(
                            partial, expectedRoleLabel,
                            OLED_PWM_MOVE_MIN, *glyphs, *connected);
                }
            }
            *partialPos = 0;
            continue;
        }
        if (c == '\r')
            continue; // skip \r (part of \r\n); don't treat as line end or we'd send empty line on \n
        if (*partialPos < cap - 1)
            partial[(*partialPos)++] = c;
        else
        {
            // TODO: THIS SHOULD THROW SOME KIND OF BAD ERROR CONDITION
            // Buffer full before \n: discard rest of line so we don't forward a partial or get stuck
            while (from->available())
            {
                char d = (char)from->read();
                if (d == '\n' || d == '\r') break;
            }
            *partialPos = 0;
        }
    }
}

void determineRole()
{
    Serial.println(F("--- SYNC ---"));

    // Emit cached role before election so USB probe can label this port correctly
    // even when the board is probed alone (and would otherwise appear as ROLE_UNKNOWN).
    switch (loadRole())
    {
        case ROLE_FRONT: Serial.println("ROLE_HINT: FRONT"); break;
        case ROLE_LEFT:  Serial.println("ROLE_HINT: LEFT");  break;
        case ROLE_RIGHT: Serial.println("ROLE_HINT: RIGHT"); break;
        default: break;
    }

    pinMode(LED_BUILTIN, OUTPUT);
    SERIAL_LEFT.begin(BAUD_RATE);
    SERIAL_RIGHT.begin(BAUD_RATE);

    bool syncFromLeft = false, syncFromRight = false;
    unsigned long start = millis();
    unsigned long lastSync = 0;

    while (millis() - start < 3000)
    {
        // Everyone sends a SYNC_TOKEN every 10ms to see what serial lines are connected
        if (millis() - lastSync >= 10)
        {
            lastSync = millis();
            SERIAL_LEFT.println(SYNC_TOKEN);
            SERIAL_RIGHT.println(SYNC_TOKEN);
        }
        // If the left serial line is available, we're either the left follower or the leader
        if (SERIAL_LEFT.available())
        {
            String s = SERIAL_LEFT.readStringUntil('\n');
            // If the leader has sent us an ASSIGN_LEFT command, we're the left follower
            if (s.indexOf(ASSIGN_LEFT) >= 0)
            {
                currentRole = ROLE_LEFT;
                actuatorManager = new ActuatorManager(ACT_LIST_LEFT, ACT_COUNT);
                mainSerial = &SERIAL_LEFT;
                saveRole(ROLE_LEFT);
                Serial.println(F("ROLE: LEFT"));
                return;
            }
            if (s.indexOf(SYNC_TOKEN) >= 0) syncFromLeft = true;
        }
        if (SERIAL_RIGHT.available())
        {
            String s = SERIAL_RIGHT.readStringUntil('\n');
            // If the leader has sent us an ASSIGN_RIGHT command, we're the right follower
            if (s.indexOf(ASSIGN_RIGHT) >= 0)
            {
                currentRole = ROLE_RIGHT;
                actuatorManager = new ActuatorManager(ACT_LIST_RIGHT, ACT_COUNT);
                mainSerial = &SERIAL_RIGHT;
                saveRole(ROLE_RIGHT);
                Serial.println(F("ROLE: RIGHT"));
                return;
            }
            if (s.indexOf(SYNC_TOKEN) >= 0) syncFromRight = true;
        }
        // Received SYNC from both sides: we are the leader. Assign followers then set ourselves as FRONT.
        if (syncFromLeft && syncFromRight)
        {
            SERIAL_LEFT.println(ASSIGN_LEFT);
            SERIAL_RIGHT.println(ASSIGN_RIGHT);
            currentRole = ROLE_FRONT;
            actuatorManager = new ActuatorManager(ACT_LIST_FRONT, ACT_COUNT);
            mainSerial = &Serial;
            leftSerial = &SERIAL_LEFT;
            rightSerial = &SERIAL_RIGHT;
            saveRole(ROLE_FRONT);
            Serial.println(F("ROLE: FRONT"));
            return;
        }
    }

    // Timeout: no both-sync, default to front actuators but report UNKNOWN.
    currentRole = ROLE_UNKNOWN;
    actuatorManager = new ActuatorManager(ACT_LIST_FRONT, ACT_COUNT);
    mainSerial = &Serial;
    leftSerial = &SERIAL_LEFT;
    rightSerial = &SERIAL_RIGHT;
    Serial.println(F("ROLE: UNKNOWN (front actuators)"));
}

void setup()
{
    Serial.begin(BAUD_RATE);
    determineRole();

    // TODO: This should not need to be done here, it should be done when actuators are instantiated, and we should delay instantiation until after role election is complete.
    LinearActuator** list = (currentRole == ROLE_LEFT) ? ACT_LIST_LEFT : (currentRole == ROLE_RIGHT) ? ACT_LIST_RIGHT : ACT_LIST_FRONT;
    for (size_t i = 0; i < ACT_COUNT; i++)
        list[i]->setControlConfig(ACTUATOR_CONFIG);
    actuatorManager->initAll();
    hallHwInit();
    actuatorManager->loadCalibration();

    if (isI2CClusterBoard())
    {
        // AC-2g: dedicated disconnect-status LED, driven each tick from loop().
        pinMode(STATUS_LED_PIN, OUTPUT);
        digitalWrite(STATUS_LED_PIN, LOW);

        imuSetup(true);
        inaSetup();
        oledValid = oled.begin();
        if (oledValid)
        {
            oled.setFont(QW_FONT_5X7);
            oledRenderLive();  // first frame is rendered before the loop
            Serial.println(F("OLED: online at 0x3D — krab UI live."));
        }
        else
            Serial.println(F("OLED: init FAILED (0x3D absent? check Qwiic seating)."));
    }

    Serial.print(F("Krabby Ready "));
    Serial.print(boardPinRevisionLabel());
    Serial.print(F(". "));
    Serial.println(list[0]->name);
}

// Read lines from a follower serial until one starts with "VER "; discard telemetry lines.
static String readVerLine(HardwareSerial* port, unsigned long timeout_ms)
{
    unsigned long deadline = millis() + timeout_ms;
    String line = "";
    while (millis() < deadline)
    {
        if (!port->available()) continue;
        char c = (char)port->read();
        if (c == '\n')
        {
            if (line.startsWith("VER ")) return line;
            line = "";
            continue;
        }
        if (c != '\r') line += c;
        if (line.length() > 128) line = ""; // guard against runaway
    }
    return "";
}

// Parse a per-board VER reply: "VER <version> <branch> <commit>"
static void parseVerToken(const String& reply, String& ver, String& branch, String& commit)
{
    ver = "-"; branch = "-"; commit = "-";
    if (!reply.startsWith("VER ")) return;
    String rest = reply.substring(4);
    int sp1 = rest.indexOf(' ');
    if (sp1 < 0) { ver = rest; return; }
    ver = rest.substring(0, sp1);
    rest = rest.substring(sp1 + 1);
    int sp2 = rest.indexOf(' ');
    if (sp2 < 0) { branch = rest; return; }
    branch = rest.substring(0, sp2);
    commit = rest.substring(sp2 + 1);
    commit.trim();
}

void loop()
{
    while (mainSerial->available())
    {
        char cmdType = mainSerial->peek();
        if (cmdType == 'T')
        {
            mainSerial->read();
            String payload = mainSerial->readStringUntil('\n');
            size_t cmdCount = parseCommands(payload, cmdBuf, CMD_BUF_SIZE);
            // Keeping it simple, we send all commands to all actuator managers, and let each actuator manager ignore any commands that aren't for them
            actuatorManager->applyCommands(cmdBuf, cmdCount);
            if (leftSerial)  { leftSerial->print("T ");  leftSerial->println(payload); }
            if (rightSerial) { rightSerial->print("T "); rightSerial->println(payload); }
        }
        else if (cmdType == 'B')
        {
            mainSerial->read();
            while (mainSerial->available() && mainSerial->peek() == ' ')
                mainSerial->read();
            if(leftSerial) leftSerial->print("B ");
            if(rightSerial) rightSerial->print("B ");
            while (true)
            {
                String name = mainSerial->readStringUntil(' ');
                int pwm = mainSerial->readStringUntil(' ').toInt();

                actuatorManager->handleJog(name, pwm);
                if (leftSerial)  { 
                    leftSerial->print(name);
                    leftSerial->print(" ");
                    leftSerial->print(pwm);
                    leftSerial->print(" ");
                }
                if (rightSerial) { 
                    rightSerial->print(name);
                    rightSerial->print(" ");
                    rightSerial->print(pwm);
                    rightSerial->print(" ");
                }
                if(mainSerial->peek() == '\n') { mainSerial->readStringUntil('\n'); break; }
            }
            if (leftSerial)  { leftSerial->println(); }
            if (rightSerial) { rightSerial->println(); }
        }
        else if (cmdType == 'J')
        {
            mainSerial->read();
            String name = mainSerial->readStringUntil(' ');
            int pwm = mainSerial->readStringUntil('\n').toInt();
            actuatorManager->handleJog(name, pwm);
            if (leftSerial)  { leftSerial->print("J ");  leftSerial->print(name);  leftSerial->print(" ");  leftSerial->println(pwm); }
            if (rightSerial) { rightSerial->print("J "); rightSerial->print(name); rightSerial->print(" "); rightSerial->println(pwm); }
        }
        else if (cmdType == 'C')
        {
            mainSerial->read();
            String payload = mainSerial->readStringUntil('\n');
            handleCalibrationCommand(payload);
        }
        else if (cmdType == 'H')
        {
            mainSerial->read();
            mainSerial->readStringUntil('\n');
            actuatorManager->holdAll();
            if (leftSerial)  leftSerial->println("H");
            if (rightSerial) rightSerial->println("H");
        }
        else if (cmdType == 'V')
        {
            mainSerial->read();
            mainSerial->readStringUntil('\n');

            if (currentRole == ROLE_LEFT || currentRole == ROLE_RIGHT)
            {
                // Follower: reply with own version on mainSerial (uplink to leader)
                mainSerial->print("VER ");
                mainSerial->print(KRABBY_FW_VERSION);
                mainSerial->print(" ");
                mainSerial->print(KRABBY_FW_BRANCH);
                mainSerial->print(" ");
                mainSerial->println(KRABBY_FW_COMMIT);
            }
            else
            {
                // Leader (FRONT or UNKNOWN): collect follower versions, combine, reply to host
                String lVer = "-", lBranch = "-", lCommit = "-";
                String rVer = "-", rBranch = "-", rCommit = "-";

                if (leftSerial)
                {
                    leftSerial->println("V");
                    String reply = readVerLine(leftSerial, 300);
                    parseVerToken(reply, lVer, lBranch, lCommit);
                }
                if (rightSerial)
                {
                    rightSerial->println("V");
                    String reply = readVerLine(rightSerial, 300);
                    parseVerToken(reply, rVer, rBranch, rCommit);
                }

                mainSerial->print("VER ");
                mainSerial->print(KRABBY_FW_VERSION); mainSerial->print("|"); mainSerial->print(lVer); mainSerial->print("|"); mainSerial->print(rVer);
                mainSerial->print(" ");
                mainSerial->print(KRABBY_FW_BRANCH); mainSerial->print("|"); mainSerial->print(lBranch); mainSerial->print("|"); mainSerial->print(rBranch);
                mainSerial->print(" ");
                mainSerial->print(KRABBY_FW_COMMIT); mainSerial->print("|"); mainSerial->print(lCommit); mainSerial->print("|"); mainSerial->println(rCommit);
            }
        }
        else
        {
            String s = mainSerial->readStringUntil('\n');
            // If leader (or another board) sent SYNC, reply so a restarted leader can discover us
            if (s.indexOf(SYNC_TOKEN) >= 0)
                mainSerial->println(SYNC_TOKEN);
        }
    }

    // Drain follower serial so RX buffers don't overflow (64-byte default drops middle of ~200-byte lines).
    // Only flush once after both drains so we don't block in flush() twice per loop (~35 ms each at 115200).
    forwardFullLines(
        leftSerial, mainSerial, leftPartial, TELEMETRY_LINE_MAX,
        &leftPartialPos, roleName(ROLE_LEFT), &followerLeftFreshness,
        &followerLeftGlyphs, &followerLeftConnected);
    forwardFullLines(
        rightSerial, mainSerial, rightPartial, TELEMETRY_LINE_MAX,
        &rightPartialPos, roleName(ROLE_RIGHT), &followerRightFreshness,
        &followerRightGlyphs, &followerRightConnected);

    actuatorManager->updateAll();

    // Drain again in case bytes arrived during updateAll()
    forwardFullLines(
        leftSerial, mainSerial, leftPartial, TELEMETRY_LINE_MAX,
        &leftPartialPos, roleName(ROLE_LEFT), &followerLeftFreshness,
        &followerLeftGlyphs, &followerLeftConnected);
    forwardFullLines(
        rightSerial, mainSerial, rightPartial, TELEMETRY_LINE_MAX,
        &rightPartialPos, roleName(ROLE_RIGHT), &followerRightFreshness,
        &followerRightGlyphs, &followerRightConnected);
    mainSerial->flush();

    const uint32_t telemetryNow = millis();
    if (telemetryPollDue(telemetryNow, lastTelemetry))
    {
        lastTelemetry = telemetryNow;
        mainSerial->print(roleName(currentRole));
        mainSerial->print(TELEMETRY_SEGMENT_DELIMITER);
        mainSerial->print(TELEMETRY_FIELD_DELIMITER);
        actuatorManager->printTelemetry(*mainSerial);
        // Leader appends its sensor segments to its own line only; forwarded
        // LEFT/RIGHT lines pass through forwardFullLines() untouched.
        if (isI2CClusterBoard())
        {
            imuAppendTelemetry(*mainSerial);
            battAppendTelemetry(*mainSerial);
        }
        mainSerial->println();
        mainSerial->flush();  // ensure full line is sent before next loop (avoids two "LEFT;" in one buffer on host)
    }

    // AC-2g: light the dedicated status LED when any known actuator is
    // disconnected. A stale/missing follower is a controller-presence fault,
    // not evidence that a specific motor is disconnected, so only fresh remote
    // snapshots participate. STATUS_LED_PIN is shared with Task 4's low-battery
    // blink, whose low-power path returns before this line.
    if (isI2CClusterBoard())
    {
        bool localConnected[6];
        for (int actuator = 0; actuator < 6; ++actuator)
            localConnected[actuator] = ACT_LIST_FRONT[actuator]->isConnected();

        ControllerSlotLinks slots = controllerSlotLinks(
            currentRole, leftSerial != NULL, rightSerial != NULL);
        uint32_t now = millis();
        bool leftFresh = controllerTelemetryIsFresh(
            slots.leftAssigned, followerLeftFreshness,
            now, OLED_PRESENCE_MS);
        bool rightFresh = controllerTelemetryIsFresh(
            slots.rightAssigned, followerRightFreshness,
            now, OLED_PRESENCE_MS);
        bool ledActive = disconnectStatusLedActive(
            localConnected,
            leftFresh, followerLeftConnected,
            rightFresh, followerRightConnected);
        digitalWrite(STATUS_LED_PIN, ledActive ? HIGH : LOW);
    }

    // OLED krab status render, throttled off the gait/telemetry cadence. A
    // changed frame uses the OLED driver's dirty-page transfer at 400 kHz; an
    // unchanged frame is skipped inside oledRenderKrab (no I2C at all).
    // Leader/solo board only.
    if (oledValid && millis() - lastOledDraw >= OLED_REDRAW_INTERVAL_MS)
    {
        lastOledDraw = millis();
        oledRenderLive();
    }
}
