#pragma once

// Arduino -> host telemetry wire tokens. Keep these separate from sensor
// configuration: punctuation and tags are protocol, not I2C settings.
static const char TELEMETRY_SEGMENT_DELIMITER = ';';
static const char TELEMETRY_FIELD_DELIMITER = ' ';
static const char IMU_TELEMETRY_TAG[] = "IMU";
