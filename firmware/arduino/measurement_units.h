#pragma once

#include <stdint.h>
class Volts
{
public:
    explicit constexpr Volts(float value) : value_(value) {}

    constexpr float value() const { return value_; }

private:
    float value_;
};

class Ohms
{
public:
    explicit constexpr Ohms(float value) : value_(value) {}

    constexpr float value() const { return value_; }

private:
    float value_;
};

class MilliAmps
{
public:
    explicit constexpr MilliAmps(float value) : value_(value) {}

    constexpr float value() const { return value_; }

private:
    float value_;
};

class Amps
{
public:
    explicit constexpr Amps(float value) : value_(value) {}

    constexpr float value() const { return value_; }

private:
    float value_;
};

class MilliWatts
{
public:
    explicit constexpr MilliWatts(float value) : value_(value) {}

    constexpr float value() const { return value_; }

private:
    float value_;
};

class Watts
{
public:
    explicit constexpr Watts(float value) : value_(value) {}

    constexpr float value() const { return value_; }

private:
    float value_;
};

class Coulombs
{
public:
    explicit constexpr Coulombs(float value) : value_(value) {}

    constexpr float value() const { return value_; }

private:
    float value_;
};

class Milliseconds
{
public:
    explicit constexpr Milliseconds(uint32_t value) : value_(value) {}

    constexpr uint32_t value() const { return value_; }

private:
    uint32_t value_;
};

constexpr Amps toAmps(MilliAmps current)
{
    return Amps(current.value() / 1000.0f);
}

constexpr MilliAmps toMilliAmps(Amps current)
{
    return MilliAmps(current.value() * 1000.0f);
}

constexpr Watts toWatts(MilliWatts power)
{
    return Watts(power.value() / 1000.0f);
}

constexpr MilliWatts toMilliWatts(Watts power)
{
    return MilliWatts(power.value() * 1000.0f);
}

inline Amps applyShuntTrim(Amps current, float trim)
{
    return Amps(current.value() * trim);
}

inline Watts applyShuntTrim(Watts power, float trim)
{
    return Watts(power.value() * trim);
}

inline Coulombs applyShuntTrim(Coulombs charge, float trim)
{
    return Coulombs(charge.value() * trim);
}
