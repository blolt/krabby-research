#pragma once

static constexpr float METERS_PER_SECOND_SQUARED_PER_G = 9.80665f;
static constexpr float RADIANS_PER_DEGREE = 0.017453293f;

struct DegreesPerSecond;

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

constexpr RadiansPerSecond DegreesPerSecond::toRadiansPerSecond() const
{
    return RadiansPerSecond(value * RADIANS_PER_DEGREE);
}

constexpr DegreesPerSecond RadiansPerSecond::toDegreesPerSecond() const
{
    return DegreesPerSecond(value / RADIANS_PER_DEGREE);
}
