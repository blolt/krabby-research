/*
 * Krabby-Uno: 18-Joint Distributed Controller (3 boards × 6 actuators)
 * Front: FL + FR, on USB. Left: RL + ML, on pins 14/15 (Serial3). Right: MR + RR, on pins 16/17 (Serial2).
 * All three boards use the same pinout; role election selects which 6 actuators this board drives.
 */

#include <Arduino.h>
#include <EEPROM.h>
#include <math.h>
#include "src/imu/imu_calibrator.h"
#include "src/imu/lsm6dso_adapter.h"
#include "src/display/ssd1306_adapter.h"
#include "src/display/display.h"
#include "board_pins.h"
#include "command.h"
#include "actuator_manager.h"
#include "src/imu/imu_constants.h"
#include "src/telemetry.h"
#include <Adafruit_INA228.h>
#include "src/power_bus/battery_level.h"
#include "src/power_bus/battery_split.h"
#include "src/power_bus/ina228_adapter.h"
#include "src/power_bus/ina_voltage.h"
#include "src/power_bus/shunt_calibration.h"
#include "src/power_bus/voltage_calibration.h"
#include "src/power_bus/power_calibration_protocol.h"
#include "src/power_bus/power_calibration_storage.h"
#include "src/power_bus/power_bus_constants.h"
#include "version.h"

// --- Serial: left follower = Serial1 (TX1/RX1 on Krabby-Uno v0.1 shield), right follower = Serial2 ---
#define SERIAL_LEFT  Serial1  // pins 18 (TX1), 19 (RX1) — Krabby-Uno v0.1 shield Serial1 connector
#define SERIAL_RIGHT Serial2   // pins 16 (TX2), 17 (RX2) — Krabby-Uno v0.1 shield Serial2 connector
#define BAUD_RATE 250000
#define SYNC_TOKEN "SYNC"
#define ASSIGN_LEFT  "ROLE:LEFT"
#define ASSIGN_RIGHT "ROLE:RIGHT"

enum BoardRole { ROLE_UNKNOWN, ROLE_FRONT, ROLE_LEFT, ROLE_RIGHT };
BoardRole currentRole = ROLE_UNKNOWN;

ControllerDisplayState leftControllerDisplayState;
ControllerDisplayState rightControllerDisplayState;
ImuMeasurement latestImuMeasurement;
Ssd1306Adapter oledDisplay;
unsigned long lastOledDrawMilliseconds = 0;
constexpr unsigned long OLED_REDRAW_INTERVAL_MILLISECONDS = 250;

// 2h.1 compares loop timing with the panel off against every eligible refresh
// doing a full transfer. Neither condition is reachable in normal operation, so
// the "O" command selects between them. Normal is the default and the only mode
// a shipped board ever leaves boot in.
enum OledRefreshMode : uint8_t
{
    OLED_REFRESH_OFF,
    OLED_REFRESH_NORMAL,
    OLED_REFRESH_FORCED,
};
static uint8_t oledRefreshMode = OLED_REFRESH_NORMAL;

// M16 I2C sensor cluster (IMU; later OLED/INA228/power mgmt) is leader-only.
// ROLE_UNKNOWN also qualifies: it is the solo-board-on-USB bench case (defaults
// to front actuators + USB serial), not a follower.
static inline bool isI2CClusterBoard()
{
    return currentRole == ROLE_FRONT || currentRole == ROLE_UNKNOWN;
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

// StatusDisplayRole → which 6 actuators this board drives (no mutation)
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

// TELEMETRY_INTERVAL_MS is the existing actuator telemetry cadence.
unsigned long lastTelemetry = 0;
// True for the one iteration following a telemetry emission — the only point in
// the cycle with a whole slot of headroom for a blocking I2C transfer.
bool telemetryJustEmitted = false;

// INA228 power monitors (Task 3): Pack measures total pack V/I/P/charge across
// the external shunt; Midpoint senses only the series junction's bus voltage,
// its current inputs tied to Pack-. Leader-only, sharing the IMU/OLED bus.
// Each owns its own liveness so one missing board cannot suppress the other.
Ina228Monitor inaPack(INA228_PACK_I2C_ADDR, /*configuresShunt=*/true);
Ina228Monitor inaMidpoint(INA228_MID_I2C_ADDR, /*configuresShunt=*/false);

// Per-board VBUS offset trims and the shunt scale (AC 3i), captured on the bench
// against a DMM and persisted with a magic-last write so a torn write reloads as
// identity rather than as a plausible wrong number.
static_assert(sizeof(PowerCalibrationData) == EEPROM_INA_CAL_SIZE,
              "update EEPROM_INA_CAL_SIZE in power_bus_constants.h");
constexpr PowerCalibrationStorageRules POWER_CALIBRATION_STORAGE_RULES = {
    EEPROM_INA_CAL_MAGIC,
    EEPROM_INA_CAL_SCHEMA,
    INA228_CAL_MAX_VOFFSET_V,
    INA228_CAL_MIN_GAIN,
    INA228_CAL_MAX_GAIN};
PowerCalibrationData inaCal = identityPowerCalibration();

// Latest battery measurement, kept for the panel. The BATT segment goes out on
// the power-poll cadence while the OLED redraws on its own, so the renderer
// reads the last measurement rather than sampling the monitors itself.
Volts latestPackVoltage;
float latestBatteryLevel[2] = {0.0f, 0.0f};
// Both monitors' liveness from the most recent poll, which is what the OLED
// needs to know. No timestamp: the poll reports the failure directly.
bool latestBatteryValid = false;
// Last trustworthy per-monitor readings, so a failed monitor's fields carry its
// last good numbers rather than the driver's failure sentinel.
struct LastGoodPack { Volts voltage; Amps current; Watts power; Coulombs charge; };
LastGoodPack lastGoodPack = {Volts(0.0f), Amps(0.0f), Watts(0.0f), Coulombs(0.0f)};
Volts lastGoodMidpointVoltage(0.0f);
BatterySplit lastGoodSplit = {0.0f, 0.0f, false};
bool latestBatteryEverUpdated = false;

// --- I2C sensor cluster (Milestone 16) — leader board only ---
// The LSM6DSO IMU rides the leader's telemetry tick; followers never touch the bus.
Lsm6dsoAdapter imuSensor;
static_assert(
    sizeof(ImuCalibrationRecord) == EEPROM_IMU_CAL_SIZE,
    "update EEPROM_IMU_CAL_SIZE in src/imu/imu_constants.h");

// EEPROM binding for ImuCalibrator. Kept out of src/imu/ because it needs
// <EEPROM.h> and that directory compiles on the host.
class EepromImuCalibrationStorage
{
public:
    void load(ImuCalibrationRecord &record)
    {
        EEPROM.get(EEPROM_IMU_CAL_ADDR, record);
    }

    void writeRecord(const ImuCalibrationRecord &record)
    {
        EEPROM.put(EEPROM_IMU_CAL_ADDR, record);
    }

    void updateMagic(uint8_t magic)
    {
        EEPROM.update(EEPROM_IMU_CAL_ADDR, magic);
    }
};

static void logImuInitFailure(Lsm6dsoInitializationResult result)
{
    if (result == Lsm6dsoInitializationResult::NotDetected)
    {
        Serial.println(F("IMU CAL: LSM6DSO not detected at configured addresses; shipping valid=0."));
        return;
    }

    if (result == Lsm6dsoInitializationResult::ConfigurationFailed)
    {
        Serial.println(F("IMU CAL: LSM6DSO detected but register configuration failed; shipping valid=0."));
        return;
    }

    Serial.println(F("IMU CAL: unexpected initialization result; shipping valid=0."));
}

static void logImuCalibrationResult(ImuCalibrationResult result)
{
    switch (result)
    {
        case ImuCalibrationResult::Loaded:
            Serial.println(F("IMU CAL: loaded from EEPROM."));
            break;
        case ImuCalibrationResult::Captured:
            Serial.println(F("IMU CAL: gyro bias captured and saved to EEPROM."));
            break;
        case ImuCalibrationResult::ReadFailed:
            Serial.println(F("IMU CAL: sensor read failed; bias left at zero, not saved."));
            break;
        case ImuCalibrationResult::MotionDetected:
            Serial.println(F("IMU CAL: motion detected; bias left at zero, not saved."));
            break;
        case ImuCalibrationResult::VerificationFailed:
            Serial.println(F("IMU CAL: EEPROM verification failed; bias left at zero."));
            break;
    }
}

static StatusDisplayRole displayRole(BoardRole role)
{
    switch (role)
    {
        case ROLE_FRONT: return StatusDisplayRole::Front;
        case ROLE_LEFT: return StatusDisplayRole::Left;
        case ROLE_RIGHT: return StatusDisplayRole::Right;
        default: return StatusDisplayRole::Unknown;
    }
}

static StatusDisplayModel currentDisplayModel()
{
    ActuatorGlyph localGlyphs[CONTROLLER_ACTUATOR_COUNT];
    for (size_t actuator = 0; actuator < CONTROLLER_ACTUATOR_COUNT; ++actuator)
        localGlyphs[actuator] = actuatorGlyphForCommandedDrive(
            ACT_LIST_FRONT[actuator]->isConnected(),
            ACT_LIST_FRONT[actuator]->currentPwm,
            ACTUATOR_CONFIG.pwmDeadband,
            ACT_LIST_FRONT[actuator]->attachmentVerified());

    return buildStatusDisplayModel(
        displayRole(currentRole),
        isI2CClusterBoard(),
        localGlyphs,
        leftControllerDisplayState, leftSerial != nullptr,
        rightControllerDisplayState, rightSerial != nullptr,
        latestImuMeasurement,
        latestPackVoltage,
        latestBatteryLevel,
        latestBatteryValid,
        millis());
}

static void updateDisconnectStatusLed()
{
    bool localConnected[CONTROLLER_ACTUATOR_COUNT];
    for (size_t actuator = 0; actuator < CONTROLLER_ACTUATOR_COUNT; ++actuator)
        localConnected[actuator] = ACT_LIST_FRONT[actuator]->isConnected();

    const uint32_t now = millis();
    digitalWrite(
        STATUS_LED_PIN,
        anyActuatorDisconnected(
            localConnected,
            leftControllerDisplayState,
            isControllerDisplayStateFresh(
                leftControllerDisplayState, leftSerial != nullptr, now),
            rightControllerDisplayState,
            isControllerDisplayStateFresh(
                rightControllerDisplayState, rightSerial != nullptr, now))
            ? HIGH
            : LOW);
}

// Bring both monitors up on the bus imuSetup() already began. Per-device: a
// missing board must not block the other. The Pack accumulator is zeroed here so
// pack_charge counts from this boot; a later recovery deliberately does not.
static void inaPersistCal()
{
    persistPowerCalibration(
        EEPROM, EEPROM_INA_CAL_ADDR, POWER_CALIBRATION_STORAGE_RULES, inaCal);
}

static void printPowerCalibration()
{
    // F() keeps these literals in flash; this bench-only text would otherwise
    // cost most of a kilobyte of the Mega's 8 KB of SRAM.
    Serial.print(F("POWER CAL: packVoltageOffset=")); Serial.print(inaCal.packVoltageOffset, 4);
    Serial.print(F(" midpointVoltageOffset="));      Serial.print(inaCal.midpointVoltageOffset, 4);
    Serial.print(F(" packShuntCal="));               Serial.println(inaCal.packShuntCal, 5);
}

static void printPowerCalibrationUsage()
{
    Serial.println(F("POWER CAL usage (leader bench only):"));
    Serial.println(F("  C PWR_SENSE VOLTAGE <packReferenceVolts> <midpointReferenceVolts>"));
    Serial.println(F("  C PWR_SENSE CURRENT <knownAmps>"));
    Serial.println(F("  C PWR_SENSE SHOW"));
    Serial.println(F("  C PWR_SENSE ?"));
}

// One calibration command, the leading 'C' already consumed. Bare C keeps the
// existing whole-controller actuator calibration; C PWR_SENSE is leader-only and
// is never forwarded to followers.
//
// Every path that could produce a bad number returns BEFORE writing, so a
// mistyped bench reference leaves the previous calibration untouched.
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

    if (command.operation == PowerCalibrationOperation::Show)
    {
        printPowerCalibration();
        return;
    }
    if (command.operation == PowerCalibrationOperation::Help)
    {
        printPowerCalibrationUsage();
        return;
    }

    // Gate each capture on exactly the monitors it reads, so a Pack-only shunt
    // trim still works with the Midpoint board absent.
    if (!inaPack.isUp())
    {
        Serial.println(F("POWER CAL: Pack monitor offline; aborting (no write)."));
        return;
    }

    if (command.operation == PowerCalibrationOperation::Voltage)
    {
        if (!inaMidpoint.isUp())
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
                inaPack.device(), inaMidpoint.device(),
                Volts(command.firstReference),
                Volts(command.secondReference),
                limits, offsets))
        {
            Serial.println(F("POWER CAL: invalid reference, reading, or solved offset; aborting (no write)."));
            return;
        }
        inaCal.packVoltageOffset = offsets.packVoltageOffset.value;
        inaCal.midpointVoltageOffset = offsets.midpointVoltageOffset.value;
        inaPersistCal();
        Serial.println(F("POWER CAL: voltage offsets saved and applied."));
        printPowerCalibration();
        return;
    }

    if (command.operation == PowerCalibrationOperation::Current)
    {
        // The operator forces a known current through the pack shunt, signed to
        // match the sensor's convention.
        const Amps knownCurrent(command.firstReference);
        const Amps measuredCurrent =
            toAmps(MilliAmps(inaPack.device().readCurrent()));
        float trim = inaCal.packShuntCal;
        if (!calculateShuntTrim(
                knownCurrent, measuredCurrent,
                Amps(INA228_CAL_MIN_SHUNT_TRIM_A),
                INA228_CAL_MIN_GAIN, INA228_CAL_MAX_GAIN, trim))
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

static void inaSetup()
{
    // Addresses printed from the constants rather than restated, so the boot log
    // cannot disagree with what begin() was actually given.
    const bool packUp = inaPack.begin(&Wire);
    Serial.print(F("INA: Pack (0x"));
    Serial.print(INA228_PACK_I2C_ADDR, HEX);
    Serial.println(packUp
        ? F(") online, external shunt calibrated.")
        : F(") init FAILED; BATT fields marked invalid."));

    const bool midpointUp = inaMidpoint.begin(&Wire);
    Serial.print(F("INA: Midpoint (0x"));
    Serial.print(INA228_MID_I2C_ADDR, HEX);
    Serial.println(midpointUp ? F(") online.") : F(") init FAILED."));

    Serial.println(loadPowerCalibration(
            EEPROM, EEPROM_INA_CAL_ADDR, POWER_CALIBRATION_STORAGE_RULES, inaCal)
        ? F("POWER CAL: loaded from EEPROM.")
        : F("POWER CAL: none/invalid; running identity trims."));
}

// Appends the BATT segment, or nothing.
//
// Recovery here is silent by design: a Serial print would splice boot text into
// the open telemetry line. Each monitor carries its own retry state, so a good
// Pack read cannot mask a wedged Midpoint.
static void battAppendTelemetry(Print& out)
{
    const uint32_t now = millis();

    // Both monitors are read and judged before either verdict is acted on, each
    // against its own reading. Library units are mixed - readBusVoltage() V,
    // readCurrent() mA, readPower() mW, readCharge() C - which is why each is
    // wrapped in its own unit type.
    const float packV = inaPack.isUp()
        ? readCorrectedInaBusVoltage(
            inaPack.device(), Volts(inaCal.packVoltageOffset)).value
        : NAN;
    const float midpointV = inaMidpoint.isUp()
        ? readCorrectedInaBusVoltage(
            inaMidpoint.device(), Volts(inaCal.midpointVoltageOffset)).value
        : NAN;

    // isUp gates the value because a monitor that is down was not read at all.
    // The range check doubles as the liveness test: a failed I2C read returns
    // Adafruit_BusIO_Register's -1 sentinel, which scales to about 52,429 V and
    // so falls outside every plausible bound. That is load-bearing and implicit -
    // were the sentinel ever 0, BATTERY_PACK_V_MIN is 0.0 and would accept it, so
    // a dead monitor would read as a valid 0 V forever. Ina228Monitor::isPresent()
    // is the explicit test if this needs hardening.
    const bool packOk = inaPack.isUp() && batteryPackVoltageIsValid(packV);
    const bool midpointOk = inaMidpoint.isUp() && batteryCellVoltageIsValid(midpointV);
    inaPack.noteRead(packOk, &Wire, now);
    inaMidpoint.noteRead(midpointOk, &Wire, now);

    // Last trustworthy readings. The frame is emitted every tick regardless, the
    // same append-only way as the Task 1 IMU segment (TASK-3 §4), so a monitor
    // that has failed still carries its last good numbers with its valid byte
    // clear rather than suppressing the other monitor's working fields.
    if (packOk)
    {
        lastGoodPack.voltage = Volts(packV);
        lastGoodPack.current = applyShuntTrim(
            toAmps(MilliAmps(inaPack.device().readCurrent())), inaCal.packShuntCal);
        lastGoodPack.power = applyShuntTrim(
            toWatts(MilliWatts(inaPack.device().readPower())), inaCal.packShuntCal);
        lastGoodPack.charge = applyShuntTrim(
            Coulombs(inaPack.device().readCharge()), inaCal.packShuntCal);
    }
    if (midpointOk)
        lastGoodMidpointVoltage = Volts(midpointV);

    // The split needs both, so it is only recomputed when both are trustworthy;
    // otherwise the last pair stands, flagged by the valid bytes.
    BatterySplit split;
    if (packOk && midpointOk &&
        calculateBatterySplit(packV, midpointV, INA228_DIVERGENCE_THRESHOLD, split))
    {
        lastGoodSplit = split;
    }

    const BatteryTelemetryFrame frame = {
        lastGoodPack.voltage,
        lastGoodPack.current,
        lastGoodPack.power,
        lastGoodPack.charge,
        Volts(lastGoodSplit.batteryA),
        Volts(lastGoodSplit.batteryB),
        lastGoodSplit.diverged,
        PACK_REGION_NORMAL,
        packOk,
        midpointOk
    };
    appendBatteryTelemetry(out, frame);

    latestBatteryValid = packOk && midpointOk;
    if (!latestBatteryValid)
        return;

    // 3g.11: the bars show the two measured batteries, not the pack average, so
    // a diverging pair is visible as two different fills rather than hidden by
    // halving the total.
    latestPackVoltage = frame.packVoltage;
    latestBatteryLevel[0] = BatteryLevel::fromVoltage(frame.batteryAVoltage).value();
    latestBatteryLevel[1] = BatteryLevel::fromVoltage(frame.batteryBVoltage).value();
}

static void imuSetup()
{
    const Lsm6dsoInitializationResult initResult =
        imuSensor.initialize();
    if (initResult != Lsm6dsoInitializationResult::Ok)
    {
        logImuInitFailure(initResult);
        return;
    }

    EepromImuCalibrationStorage storage;
    logImuCalibrationResult(imuSensor.calibrate(storage, delay));

    Serial.println(F("IMU CAL: LSM6DSO online."));
}

// One line = "ROLE; " + ACT_COUNT segments; allow ~55 chars per segment to avoid truncation.
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
    const char* expectedRole,
    ControllerDisplayState* displayState)
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
                if (displayState)
                {
                    ActuatorTelemetry actuators[CONTROLLER_ACTUATOR_COUNT];
                    if (parseActuatorTelemetry(partial, expectedRole, actuators))
                    {
                        updateControllerDisplayState(
                            *displayState, actuators,
                            ACTUATOR_CONFIG.pwmDeadband, millis());
                    }
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
    Serial.println("--- SYNC ---");

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
                Serial.println("ROLE: LEFT");
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
                Serial.println("ROLE: RIGHT");
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
            Serial.println("ROLE: FRONT");
            return;
        }
    }

    // Timeout: no both-sync, default to front actuators but report UNKNOWN.
    currentRole = ROLE_UNKNOWN;
    actuatorManager = new ActuatorManager(ACT_LIST_FRONT, ACT_COUNT);
    mainSerial = &Serial;
    leftSerial = &SERIAL_LEFT;
    rightSerial = &SERIAL_RIGHT;
    Serial.println("ROLE: UNKNOWN (front actuators)");
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
        pinMode(STATUS_LED_PIN, OUTPUT);
        digitalWrite(STATUS_LED_PIN, LOW);
        imuSetup();
        inaSetup();
        if (oledDisplay.initialize())
            oledDisplay.render(currentDisplayModel());
        else
            Serial.println(F("OLED: initialization failed at 0x3D."));
    }

    Serial.print("Krabby Ready ");
    Serial.print(boardPinRevisionLabel());
    Serial.print(". ");
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
        else if (cmdType == 'P')
        {
            // "P1" enables the AVR's internal pull-up on every local pot input,
            // "P0" returns them to high-Z. 2f.1 asks whether an open position
            // input can be forced to a rejected rail: a connected wiper is low
            // impedance and barely moves, while an open pin has nothing holding
            // it and rises to the rail.
            mainSerial->read();
            String mode = mainSerial->readStringUntil('\n');
            mode.trim();
            const bool pullUp = mode.toInt() != 0;
            for (size_t actuator = 0; actuator < CONTROLLER_ACTUATOR_COUNT; ++actuator)
                pinMode(ACT_LIST_FRONT[actuator]->pinPot, pullUp ? INPUT_PULLUP : INPUT);
        }
        else if (cmdType == 'O')
        {
            // "O0" panel off, "O1" normal, "O2" force a full transfer every refresh.
            mainSerial->read();
            String mode = mainSerial->readStringUntil('\n');
            mode.trim();
            const int requested = mode.toInt();
            if (requested >= OLED_REFRESH_OFF && requested <= OLED_REFRESH_FORCED)
                oledRefreshMode = (uint8_t)requested;
        }
        else if (cmdType == 'C')
        {
            mainSerial->read();
            handleCalibrationCommand(mainSerial->readStringUntil('\n'));
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
    forwardFullLines(leftSerial, mainSerial, leftPartial, TELEMETRY_LINE_MAX,
                     &leftPartialPos, "LEFT ", &leftControllerDisplayState);
    forwardFullLines(rightSerial, mainSerial, rightPartial, TELEMETRY_LINE_MAX,
                     &rightPartialPos, "RIGHT", &rightControllerDisplayState);

    actuatorManager->updateAll();

    if (isI2CClusterBoard())
    {
        updateDisconnectStatusLed();
        // Start a transfer only in the slot just after telemetry went out. The
        // redraw and telemetry timers are independent, so an unaligned refresh
        // can begin late in a slot and push the emission past its deadline; a
        // full frame is ~29 ms on a 50 ms tick, which fits only with the whole
        // slot ahead of it. Costs at most one telemetry period of refresh delay.
        if (oledDisplay.isInitialized() && oledRefreshMode != OLED_REFRESH_OFF &&
            telemetryJustEmitted &&
            millis() - lastOledDrawMilliseconds >= OLED_REDRAW_INTERVAL_MILLISECONDS)
        {
            lastOledDrawMilliseconds = millis();
            // 2h.1 needs the worst case measured, and an unchanged model normally
            // transfers nothing. Forcing the dirty state is the only way to make
            // every eligible refresh do real work.
            if (oledRefreshMode == OLED_REFRESH_FORCED)
                oledDisplay.invalidate();
            oledDisplay.render(currentDisplayModel());
        }
    }

    // Drain again in case bytes arrived during updateAll()
    forwardFullLines(leftSerial, mainSerial, leftPartial, TELEMETRY_LINE_MAX,
                     &leftPartialPos, "LEFT ", &leftControllerDisplayState);
    forwardFullLines(rightSerial, mainSerial, rightPartial, TELEMETRY_LINE_MAX,
                     &rightPartialPos, "RIGHT", &rightControllerDisplayState);
    mainSerial->flush();

    // Cleared here and set below, so the OLED block at the top of the next
    // iteration sees a full slot ahead of it.
    telemetryJustEmitted = false;
    // One millis() for the whole tick. Re-reading it per subsystem gave each its
    // own epoch, which is what let the power gate below drift past the period.
    const uint32_t tickNow = millis();
    if (telemetryPollDue(tickNow, lastTelemetry))
    {
        telemetryJustEmitted = true;
        lastTelemetry = tickNow;
        mainSerial->print(roleName(currentRole));
        mainSerial->print(TELEMETRY_SEGMENT_DELIMITER);
        mainSerial->print(TELEMETRY_FIELD_SEPARATOR);
        actuatorManager->printTelemetry(*mainSerial);
        // Leader appends its sensor segments to its own line only; forwarded
        // LEFT/RIGHT lines pass through forwardFullLines() untouched.
        if (isI2CClusterBoard())
        {
            const ImuMeasurement measurement = imuSensor.measure();
            latestImuMeasurement = measurement;
            appendImuMeasurement(*mainSerial, measurement);
            // Both monitors are read on this tick, at POWER_POLL_INTERVAL, which
            // is the tick period (AC 3h.6). A second gate here once stamped its
            // own timestamp later in the tick than lastTelemetry, so its period
            // was effectively 50 ms + the actuator print + the IMU read and it
            // dropped a BATT segment whenever that overran.
            battAppendTelemetry(*mainSerial);
        }
        mainSerial->println();
        mainSerial->flush();  // ensure full line is sent before next loop (avoids two "LEFT;" in one buffer on host)
    }
}
