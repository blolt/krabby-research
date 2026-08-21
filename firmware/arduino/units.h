#pragma once

#include <stdint.h>

// How a conversion treats fractional results. HalfAwayFromZero is lroundf's
// rule: 2.5 -> 3, -2.5 -> -3 (rintf would give 2 and -2).
enum class Rounding : uint8_t
{
    Exact,
    HalfAwayFromZero,
};

// lroundf written out so it is usable in a constant expression.
constexpr float roundHalfAwayFromZero(float value)
{
    return value >= 0.0f ? static_cast<float>(static_cast<long>(value + 0.5f))
                         : static_cast<float>(static_cast<long>(value - 0.5f));
}

static constexpr float METERS_PER_SECOND_SQUARED_PER_G = 9.80665f;
static constexpr float RADIANS_PER_DEGREE = 0.017453293f;


struct MetersPerSecondSquared
{
    float value;

    constexpr MetersPerSecondSquared()
        : value(0.0f)
    {
    }

    explicit constexpr MetersPerSecondSquared(float value)
        : value(value)
    {
    }
};

struct DegreesPerSecond;

struct RadiansPerSecond
{
    float value;

    constexpr RadiansPerSecond()
        : value(0.0f)
    {
    }

    explicit constexpr RadiansPerSecond(float value)
        : value(value)
    {
    }

    constexpr DegreesPerSecond toDegreesPerSecond() const;
};

struct DegreesPerSecond
{
    float value;

    constexpr DegreesPerSecond()
        : value(0.0f)
    {
    }

    explicit constexpr DegreesPerSecond(float value)
        : value(value)
    {
    }

    constexpr RadiansPerSecond toRadiansPerSecond() const;
};

struct Degrees;

struct Radians
{
    float value;

    constexpr Radians()
        : value(0.0f)
    {
    }

    explicit constexpr Radians(float value)
        : value(value)
    {
    }

    // Exact by default; rounding is opt-in for callers that compare angles
    // for equality, since only integral floats compare exactly. The Exact
    // path stays a constant expression.
    constexpr Degrees toDegrees(Rounding rounding = Rounding::Exact) const;
};

struct Degrees
{
    float value;

    constexpr Degrees()
        : value(0.0f)
    {
    }

    explicit constexpr Degrees(float value)
        : value(value)
    {
    }

    constexpr Radians toRadians() const
    {
        return Radians(value * RADIANS_PER_DEGREE);
    }
};

struct Volts
{
    float value;

    constexpr Volts()
        : value(0.0f)
    {
    }

    explicit constexpr Volts(float value)
        : value(value)
    {
    }
};

struct Celsius
{
    float value;

    constexpr Celsius()
        : value(0.0f)
    {
    }

    explicit constexpr Celsius(float value)
        : value(value)
    {
    }
};

constexpr Degrees Radians::toDegrees(Rounding rounding) const
{
    return rounding == Rounding::HalfAwayFromZero
               ? Degrees(roundHalfAwayFromZero(value / RADIANS_PER_DEGREE))
               : Degrees(value / RADIANS_PER_DEGREE);
}

constexpr RadiansPerSecond DegreesPerSecond::toRadiansPerSecond() const
{
    return RadiansPerSecond(value * RADIANS_PER_DEGREE);
}

constexpr DegreesPerSecond RadiansPerSecond::toDegreesPerSecond() const
{
    return DegreesPerSecond(value / RADIANS_PER_DEGREE);
}

// Electrical and time quantities for the power bus. Same struct shape as the
// motion units above: a named wrapper that stops a bare float standing in for
// a quantity, without yet defining operations between them.
struct Amps
{
    float value;

    constexpr Amps()
        : value(0.0f)
    {
    }

    explicit constexpr Amps(float value)
        : value(value)
    {
    }
};

struct MilliAmps
{
    float value;

    constexpr MilliAmps()
        : value(0.0f)
    {
    }

    explicit constexpr MilliAmps(float value)
        : value(value)
    {
    }
};

struct Watts
{
    float value;

    constexpr Watts()
        : value(0.0f)
    {
    }

    explicit constexpr Watts(float value)
        : value(value)
    {
    }
};

struct MilliWatts
{
    float value;

    constexpr MilliWatts()
        : value(0.0f)
    {
    }

    explicit constexpr MilliWatts(float value)
        : value(value)
    {
    }
};

// Accumulated charge, as the INA228 reports it.
struct Coulombs
{
    float value;

    constexpr Coulombs()
        : value(0.0f)
    {
    }

    explicit constexpr Coulombs(float value)
        : value(value)
    {
    }
};

struct Ohms
{
    float value;

    constexpr Ohms()
        : value(0.0f)
    {
    }

    explicit constexpr Ohms(float value)
        : value(value)
    {
    }
};

struct Milliseconds
{
    float value;

    constexpr Milliseconds()
        : value(0.0f)
    {
    }

    explicit constexpr Milliseconds(float value)
        : value(value)
    {
    }
};

// The INA228 library reports current in mA and power in mW while the telemetry
// frame carries amps and watts, so the conversion happens once here rather than
// as a bare /1000.0f at each call site.
constexpr Amps toAmps(MilliAmps current)
{
    return Amps(current.value / 1000.0f);
}

constexpr MilliAmps toMilliAmps(Amps current)
{
    return MilliAmps(current.value * 1000.0f);
}

constexpr Watts toWatts(MilliWatts power)
{
    return Watts(power.value / 1000.0f);
}

constexpr MilliWatts toMilliWatts(Watts power)
{
    return MilliWatts(power.value * 1000.0f);
}
