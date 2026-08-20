#pragma once

#include <math.h>
#include <stdint.h>

struct PotValidityLimits
{
    int minimumRaw;         // below this the input reads as railed low
    int maximumRaw;         // above this it reads as railed high
    int idleJitterMax;      // max ADC drift per sample while undriven
    uint8_t invalidSampleLimit;  // consecutive bad samples before invalid
    int openProbeMinimum;   // probed reading at or above this means the input is open
    int openProbeMargin;    // added to a calibrated maxStop instead of the above
};

// Probe thresholds are bench-measured with the AVR's internal pull-up enabled:
// the one channel with a pot attached moved 2 counts, while five disconnected
// inputs rose from 155-456 to 1005-1020.
constexpr PotValidityLimits POT_VALIDITY_DEFAULT_LIMITS = {5, 1018, 6, 3, 1000, 10};

// Highest raw value a stroke can reach; also the uncalibrated default for
// LinearActuator::maxStop, which is how an uncalibrated channel is recognised.
constexpr int POT_STROKE_MAX_RAW = 1023;

// A channel whose stroke has been calibrated knows the highest a connected wiper
// reaches, so its threshold can sit just above that rather than at a value chosen
// for the worst actuator. The derived value is allowed to exceed the default: a
// pot that genuinely reaches 1010 would be called open by a fixed 1000.
inline int potOpenProbeMinimum(int maxStop, const PotValidityLimits &limits)
{
    return maxStop >= POT_STROKE_MAX_RAW
        ? limits.openProbeMinimum
        : maxStop + limits.openProbeMargin;
}

class PotValidityTracker
{
public:
    PotValidityTracker()
        : previousRawPot_(0), badSampleCount_(0), valid_(true), positionOpen_(false)
    {
    }

    bool isValid() const { return valid_ && !positionOpen_; }

    void reset(int seedRawPot)
    {
        previousRawPot_ = seedRawPot;
        badSampleCount_ = 0;
        valid_ = true;
        positionOpen_ = false;
    }

    // Result of reading the pin with the internal pull-up enabled. A connected
    // wiper is low impedance and barely moves; an open input has nothing holding
    // it and rises to the rail. The separation is ~800 counts, so one reading is
    // conclusive and no debounce is needed — and it is held apart from the
    // sampled verdict so neither can mask the other.
    void notePositionProbe(int probedRaw, int openMinimum)
    {
        positionOpen_ = probedRaw >= openMinimum;
    }

    bool positionOpen() const { return positionOpen_; }

    bool update(int rawPot, bool driving, const PotValidityLimits &limits)
    {
        const bool inSaneBand =
            rawPot > limits.minimumRaw && rawPot < limits.maximumRaw;
        int delta = rawPot - previousRawPot_;
        if (delta < 0)
            delta = -delta;
        previousRawPot_ = rawPot;

        const bool slewValid = driving || delta <= limits.idleJitterMax;
        if (inSaneBand && slewValid)
            badSampleCount_ = 0;
        else if (badSampleCount_ < limits.invalidSampleLimit)
            ++badSampleCount_;

        valid_ = badSampleCount_ < limits.invalidSampleLimit;
        // Returns the composed verdict, not the sample half, so a caller reading
        // this cannot disagree with one reading isValid().
        return isValid();
    }

private:
    int previousRawPot_;
    uint8_t badSampleCount_;  // saturates at invalidSampleLimit
    bool valid_;
    bool positionOpen_;
};

inline float filteredActuatorPosition(bool connected, float normalizedPosition)
{
    return connected ? normalizedPosition : (float)NAN;
}
