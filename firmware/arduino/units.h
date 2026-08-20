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
