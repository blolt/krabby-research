#pragma once

#include <stdint.h>

enum class ActuatorAttachmentState : uint8_t
{
    Unknown,
    Attached,
    Disconnected,
};

struct ActuatorAttachmentLimits
{
    int currentPresentFloor;  // ADC counts that count as current flowing
    int probePwm;             // min |PWM| before the reading means anything
    uint8_t debounceSamples;  // consecutive samples before the state flips
};

// Bench-measured against an unloaded actuator: a driven attached channel reads
// 1-7 ADC counts, while an empty channel on the same H-bridge never exceeds 1
// and never sustains it. Current is flat across PWM 50-255, so probePwm stays at
// the low end of the usable range.
constexpr ActuatorAttachmentLimits ACTUATOR_ATTACHMENT_DEFAULT_LIMITS = {1, 50, 3};

class ActuatorAttachmentTracker
{
public:
    ActuatorAttachmentTracker()
        : state_(ActuatorAttachmentState::Unknown),
          attachedEvidenceCount_(0),
          disconnectedEvidenceCount_(0)
    {
    }

    ActuatorAttachmentState state() const { return state_; }

    void reset()
    {
        state_ = ActuatorAttachmentState::Unknown;
        attachedEvidenceCount_ = 0;
        disconnectedEvidenceCount_ = 0;
    }

    void update(
        bool currentEvidenceUsable,
        int measuredCurrent,
        const ActuatorAttachmentLimits &limits)
    {
        if (!currentEvidenceUsable || limits.debounceSamples == 0)
        {
            attachedEvidenceCount_ = 0;
            disconnectedEvidenceCount_ = 0;
            return;
        }

        if (measuredCurrent >= limits.currentPresentFloor)
        {
            disconnectedEvidenceCount_ = 0;
            if (attachedEvidenceCount_ < limits.debounceSamples)
                ++attachedEvidenceCount_;
            if (attachedEvidenceCount_ >= limits.debounceSamples)
                state_ = ActuatorAttachmentState::Attached;
            return;
        }

        attachedEvidenceCount_ = 0;
        if (disconnectedEvidenceCount_ < limits.debounceSamples)
            ++disconnectedEvidenceCount_;
        if (disconnectedEvidenceCount_ >= limits.debounceSamples)
            state_ = ActuatorAttachmentState::Disconnected;
    }

    bool isAttachedOrUnknown() const
    {
        return state_ != ActuatorAttachmentState::Disconnected;
    }

private:
    ActuatorAttachmentState state_;
    uint8_t attachedEvidenceCount_;
    uint8_t disconnectedEvidenceCount_;
};

inline bool actuatorConnectionIsValid(
    bool positionValid,
    const ActuatorAttachmentTracker &attachment)
{
    return positionValid && attachment.isAttachedOrUnknown();
}
